from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.export_utils import pdf_response
from config.auth import get_active_company_id
from .models import Vendor, PurchaseInvoice, APPayment, Item
from .serializers import VendorSerializer, PurchaseInvoiceSerializer, APPaymentSerializer, PurchaseInvoiceLineSerializer, ItemSerializer
from . import services


def _serialize_vendor(vendor):
    data = VendorSerializer(vendor).data
    data['balance'] = round(sum(
        max(0, inv.total_amount - inv.amount_paid)
        for inv in vendor.invoices.all() if inv.status in ('POSTED', 'PAID')
    ), 2)
    return data


def _serialize_item(item):
    data = ItemSerializer(item).data
    vendor = item.vendor.single()
    expense_account = item.expense_account.single()
    revenue_account = item.revenue_account.single()
    data['vendor_id'] = vendor.vendor_id if vendor else None
    data['expense_account_id'] = expense_account.account_id if expense_account else None
    data['revenue_account_id'] = revenue_account.account_id if revenue_account else None
    return data


def _serialize_invoice(invoice):
    data = PurchaseInvoiceSerializer(invoice).data
    lines = list(invoice.lines.all())
    data['lines'] = PurchaseInvoiceLineSerializer(lines, many=True).data
    vendor = invoice.vendor.single()
    ap_account = invoice.ap_account.single()
    data['vendor_id'] = vendor.vendor_id if vendor else None
    data['ap_account_id'] = ap_account.account_id if ap_account else None
    for idx, line in enumerate(lines):
        expense_account = line.expense_account.single()
        data['lines'][idx]['expense_account_id'] = expense_account.account_id if expense_account else None
    return data


class VendorViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        vendors = [v for v in Vendor.nodes.filter(company_id=company_id) if v.is_active]
        return Response([_serialize_vendor(v) for v in vendors])

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        vendor = Vendor.nodes.get_or_none(vendor_id=pk, company_id=company_id)
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_vendor(vendor))

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = VendorSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(_serialize_vendor(vendor), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        vendor = Vendor.nodes.get_or_none(vendor_id=pk, company_id=company_id)
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = VendorSerializer(vendor, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(_serialize_vendor(vendor))

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        vendor = Vendor.nodes.get_or_none(vendor_id=pk, company_id=company_id)
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        vendor.is_active = False
        vendor.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='statement')
    def statement(self, request, pk=None):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        data = services.get_vendor_statement(pk, company_id)
        if data is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        fmt = request.query_params.get('format', 'json')
        if fmt == 'pdf':
            return pdf_response(request, 'payables/vendor_statement.html', data, f'vendor-statement-{pk}')
        if fmt == 'xlsx':
            headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)']
            rows = [
                [l['date'], l['type'], l['reference'], l['description'], l['debit'], l['credit'], l['running_balance']]
                for l in data['lines']
            ]
            rows.append(['', '', '', '', '', 'CLOSING BALANCE', data['closing_balance']])
            return xlsx_response(request, headers, rows, f'vendor-statement-{pk}', 'Statement')
        return Response(data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        vendors = sorted([v for v in Vendor.nodes.filter(company_id=company_id) if v.is_active], key=lambda v: v.name)
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Name', 'Email', 'Phone', 'Address']
        rows = [[v.name, v.email, v.phone, v.address] for v in vendors]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['name', 'email', 'phone', 'address'], r)) for r in rows]}
            return pdf_response(request, 'payables/vendor_list.html', ctx, 'vendors')
        return xlsx_response(request, headers, rows, 'vendors', 'Vendors')


class PurchaseInvoiceViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        invoices = PurchaseInvoice.nodes.filter(company_id=company_id)
        inv_status = request.query_params.get('status')
        vendor_id = request.query_params.get('vendor_id')
        invoices = list(invoices)
        if inv_status:
            invoices = [i for i in invoices if i.status == inv_status.upper()]
        if vendor_id:
            invoices = [i for i in invoices if (v := i.vendor.single()) and v.vendor_id == vendor_id]
        invoices = sorted(invoices, key=lambda i: str(i.date), reverse=True)
        return Response(PurchaseInvoiceSerializer(invoices, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk, company_id=company_id)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_invoice(invoice))

    @action(detail=True, methods=['get'], url_path='print')
    def print_invoice(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk, company_id=company_id)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        vendor = invoice.vendor.single()
        lines = list(invoice.lines.all())
        return pdf_response('payables/purchase_invoice.html', {
            'invoice': invoice,
            'vendor': vendor,
            'lines': lines,
            'settled_amount': invoice.amount_paid,
            'outstanding_amount': max(0, invoice.total_amount - invoice.amount_paid),
        }, f'purchase-invoice-{invoice.invoice_number}')

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseInvoiceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save(created_by=request.user.username)
        return Response(_serialize_invoice(invoice), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk, company_id=company_id)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseInvoiceSerializer(invoice, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        return Response(_serialize_invoice(invoice))

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk, company_id=company_id)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        for line in list(invoice.lines.all()):
            invoice.lines.disconnect(line)
            expense_account = line.expense_account.single()
            if expense_account:
                line.expense_account.disconnect(expense_account)
            line.delete()
        vendor = invoice.vendor.single()
        if vendor:
            invoice.vendor.disconnect(vendor)
        ap_account = invoice.ap_account.single()
        if ap_account:
            invoice.ap_account.disconnect(ap_account)
        invoice.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='post')
    def post_invoice(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        company_id = get_active_company_id(request)
        try:
            invoice = services.post_invoice(pk, company_id, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_invoice(invoice))

    @action(detail=True, methods=['post'], url_path='void')
    def void_invoice(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        company_id = get_active_company_id(request)
        try:
            invoice = services.void_invoice(pk, company_id, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_invoice(invoice))

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        invoices = list(PurchaseInvoice.nodes.filter(company_id=company_id))
        invoices = sorted(invoices, key=lambda i: str(i.date), reverse=True)
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Invoice #', 'Vendor', 'Date', 'Due Date', 'Total (N)', 'Paid (N)', 'Status']
        rows = []
        for inv in invoices:
            vendor = inv.vendor.single()
            rows.append([
                inv.invoice_number, vendor.name if vendor else '', str(inv.date), str(inv.due_date),
                inv.total_amount, inv.amount_paid, inv.status,
            ])
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['invoice_number', 'vendor', 'date', 'due_date', 'total_amount', 'amount_paid', 'status'], r
            )) for r in rows]}
            return pdf_response(request, 'payables/invoice_list.html', ctx, 'purchase-invoices')
        return xlsx_response(request, headers, rows, 'purchase-invoices', 'Purchase Invoices')

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        company_id = get_active_company_id(request)
        payment_date = request.data.get('payment_date')
        amount = request.data.get('amount')
        reference = request.data.get('reference', '')
        bank_account_id = request.data.get('bank_account_id')
        if not all([payment_date, amount, bank_account_id]):
            return Response({'detail': 'payment_date, amount, and bank_account_id are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'amount must be a valid number.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payment = services.record_payment(
                pk, company_id, payment_date, amount, reference, bank_account_id, request.user.username
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(APPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class ItemViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        items = [i for i in Item.nodes.filter(company_id=company_id) if i.is_active]
        return Response([_serialize_item(i) for i in items])

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        item = Item.nodes.get_or_none(item_id=pk, company_id=company_id)
        if not item:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_item(item))

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ItemSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(_serialize_item(item), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        item = Item.nodes.get_or_none(item_id=pk, company_id=company_id)
        if not item:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ItemSerializer(item, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(_serialize_item(item))

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        item = Item.nodes.get_or_none(item_id=pk, company_id=company_id)
        if not item:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        item.is_active = False
        item.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        items = sorted([i for i in Item.nodes.filter(company_id=company_id) if i.is_active], key=lambda i: i.name)
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Name', 'Type', 'Vendor', 'Cost Price (N)', 'Selling Price (N)']
        rows = []
        for i in items:
            vendor = i.vendor.single()
            rows.append([i.name, i.item_type, vendor.name if vendor else '', i.cost_price, i.selling_price])
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'item_type', 'vendor', 'cost_price', 'selling_price'], r
            )) for r in rows]}
            return pdf_response(request, 'payables/item_list.html', ctx, 'items')
        return xlsx_response(request, headers, rows, 'items', 'Items')
