from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.export_utils import pdf_response
from config.auth import get_active_company_id
from .models import Vendor, PurchaseInvoice, APPayment, Item
from .serializers import VendorSerializer, PurchaseInvoiceSerializer, APPaymentSerializer, PurchaseInvoiceLineSerializer, ItemSerializer
from . import services


class VendorViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        vendors = Vendor.objects.filter(company_id=company_id, is_active=True)
        return Response(VendorSerializer(vendors, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        vendor = Vendor.objects.filter(vendor_id=pk, company_id=company_id).first()
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(VendorSerializer(vendor).data)

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = VendorSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(VendorSerializer(vendor).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        vendor = Vendor.objects.filter(vendor_id=pk, company_id=company_id).first()
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = VendorSerializer(vendor, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(VendorSerializer(vendor).data)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        vendor = Vendor.objects.filter(vendor_id=pk, company_id=company_id).first()
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
        vendors = Vendor.objects.filter(company_id=company_id, is_active=True).order_by('name')
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
        invoices = PurchaseInvoice.objects.filter(company_id=company_id).select_related('vendor', 'ap_account')
        inv_status = request.query_params.get('status')
        if inv_status:
            invoices = invoices.filter(status=inv_status.upper())
        vendor_id = request.query_params.get('vendor_id')
        if vendor_id:
            invoices = invoices.filter(vendor_id=vendor_id)
        invoices = invoices.order_by('-date')
        return Response(PurchaseInvoiceSerializer(invoices, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.objects.filter(invoice_id=pk, company_id=company_id).select_related('vendor', 'ap_account').first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PurchaseInvoiceSerializer(invoice).data)

    @action(detail=True, methods=['get'], url_path='print')
    def print_invoice(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.objects.filter(invoice_id=pk, company_id=company_id).select_related('vendor').first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        lines = list(invoice.lines.select_related('expense_account').all())
        return pdf_response(request, 'payables/purchase_invoice.html', {
            'invoice': invoice,
            'vendor': invoice.vendor,
            'lines': lines,
            'settled_amount': invoice.amount_paid,
            'outstanding_amount': max(0, invoice.total_amount - invoice.amount_paid),
        }, f'purchase-invoice-{invoice.invoice_number}')

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseInvoiceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save(created_by=request.user)
        return Response(PurchaseInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.objects.filter(invoice_id=pk, company_id=company_id).first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseInvoiceSerializer(invoice, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        return Response(PurchaseInvoiceSerializer(invoice).data)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = PurchaseInvoice.objects.filter(invoice_id=pk, company_id=company_id).first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        invoice.delete()  # PurchaseInvoiceLine.invoice FK is on_delete=CASCADE
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='post')
    def post_invoice(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            invoice = services.post_invoice(pk, company_id, request.user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PurchaseInvoiceSerializer(invoice).data)

    @action(detail=True, methods=['post'], url_path='void')
    def void_invoice(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            invoice = services.void_invoice(pk, company_id, request.user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PurchaseInvoiceSerializer(invoice).data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        invoices = PurchaseInvoice.objects.filter(company_id=company_id).select_related('vendor').order_by('-date')
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Invoice #', 'Vendor', 'Date', 'Due Date', 'Total (N)', 'Paid (N)', 'Status']
        rows = [
            [
                inv.invoice_number, inv.vendor.name if inv.vendor else '', str(inv.date), str(inv.due_date),
                inv.total_amount, inv.amount_paid, inv.status,
            ]
            for inv in invoices
        ]
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
                pk, company_id, payment_date, amount, reference, bank_account_id, request.user
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(APPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class ItemViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        items = Item.objects.filter(company_id=company_id, is_active=True)
        return Response(ItemSerializer(items, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        item = Item.objects.filter(item_id=pk, company_id=company_id).first()
        if not item:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ItemSerializer(item).data)

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ItemSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ItemSerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        item = Item.objects.filter(item_id=pk, company_id=company_id).first()
        if not item:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ItemSerializer(item, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ItemSerializer(item).data)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        item = Item.objects.filter(item_id=pk, company_id=company_id).first()
        if not item:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        item.is_active = False
        item.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        items = Item.objects.filter(company_id=company_id, is_active=True).select_related('vendor').order_by('name')
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Name', 'Type', 'Vendor', 'Cost Price (N)', 'Selling Price (N)']
        rows = [
            [i.name, i.item_type, i.vendor.name if i.vendor else '', i.cost_price, i.selling_price]
            for i in items
        ]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'item_type', 'vendor', 'cost_price', 'selling_price'], r
            )) for r in rows]}
            return pdf_response(request, 'payables/item_list.html', ctx, 'items')
        return xlsx_response(request, headers, rows, 'items', 'Items')
