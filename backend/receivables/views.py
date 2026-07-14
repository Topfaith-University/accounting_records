from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Customer, SalesInvoice
from .serializers import CustomerSerializer, SalesInvoiceSerializer, ARReceiptSerializer, SalesInvoiceLineSerializer
from . import services


def _serialize_invoice(invoice):
    data = SalesInvoiceSerializer(invoice).data
    lines = list(invoice.lines.all())
    data['lines'] = SalesInvoiceLineSerializer(lines, many=True).data
    customer = invoice.customer.single()
    ar_account = invoice.ar_account.single()
    data['customer_id'] = customer.customer_id if customer else None
    data['ar_account_id'] = ar_account.account_id if ar_account else None
    for idx, line in enumerate(lines):
        revenue_account = line.revenue_account.single()
        data['lines'][idx]['revenue_account_id'] = revenue_account.account_id if revenue_account else None
    return data


class CustomerViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        customers = [c for c in Customer.nodes.all() if c.is_active]
        return Response(CustomerSerializer(customers, many=True).data)

    def retrieve(self, request, pk=None):
        customer = Customer.nodes.get_or_none(customer_id=pk)
        if not customer:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CustomerSerializer(customer).data)

    def create(self, request):
        serializer = CustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        customer = Customer.nodes.get_or_none(customer_id=pk)
        if not customer:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CustomerSerializer(customer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(CustomerSerializer(customer).data)

    def destroy(self, request, pk=None):
        customer = Customer.nodes.get_or_none(customer_id=pk)
        if not customer:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        customer.is_active = False
        customer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        customers = sorted([c for c in Customer.nodes.all() if c.is_active], key=lambda c: c.name)
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Name', 'Type', 'Email', 'Phone']
        rows = [[c.name, c.customer_type, c.email, c.phone] for c in customers]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['name', 'customer_type', 'email', 'phone'], r)) for r in rows]}
            return pdf_response('receivables/customer_list.html', ctx, 'customers')
        return xlsx_response(headers, rows, 'customers', 'Customers')


class SalesInvoiceViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        invoices = SalesInvoice.nodes.all()
        inv_status = request.query_params.get('status')
        customer_id = request.query_params.get('customer_id')
        invoices = list(invoices)
        if inv_status:
            invoices = [i for i in invoices if i.status == inv_status.upper()]
        if customer_id:
            invoices = [i for i in invoices if (c := i.customer.single()) and c.customer_id == customer_id]
        invoices = sorted(invoices, key=lambda i: str(i.date), reverse=True)
        return Response(SalesInvoiceSerializer(invoices, many=True).data)

    def retrieve(self, request, pk=None):
        invoice = SalesInvoice.nodes.get_or_none(invoice_id=pk)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_invoice(invoice))

    def create(self, request):
        serializer = SalesInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save(created_by=request.user.username)
        return Response(_serialize_invoice(invoice), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        invoice = SalesInvoice.nodes.get_or_none(invoice_id=pk)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = SalesInvoiceSerializer(invoice, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        return Response(_serialize_invoice(invoice))

    def destroy(self, request, pk=None):
        invoice = SalesInvoice.nodes.get_or_none(invoice_id=pk)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        for line in list(invoice.lines.all()):
            invoice.lines.disconnect(line)
            revenue_account = line.revenue_account.single()
            if revenue_account:
                line.revenue_account.disconnect(revenue_account)
            line.delete()
        customer = invoice.customer.single()
        if customer:
            invoice.customer.disconnect(customer)
        ar_account = invoice.ar_account.single()
        if ar_account:
            invoice.ar_account.disconnect(ar_account)
        invoice.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='post')
    def post_invoice(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            invoice = services.post_invoice(pk, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_invoice(invoice))

    @action(detail=True, methods=['post'], url_path='void')
    def void_invoice(self, request, pk=None):
        if not request.user.groups.filter(name__in=['Manager', 'Admin']).exists():
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            invoice = services.void_invoice(pk, request.user.username)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_invoice(invoice))

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        invoices = list(SalesInvoice.nodes.all())
        invoices = sorted(invoices, key=lambda i: str(i.date), reverse=True)
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Invoice #', 'Customer', 'Date', 'Due Date', 'Total (N)', 'Received (N)', 'Status']
        rows = []
        for inv in invoices:
            customer = inv.customer.single()
            rows.append([
                inv.invoice_number, customer.name if customer else '', str(inv.date), str(inv.due_date),
                inv.total_amount, inv.amount_received, inv.status,
            ])
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['invoice_number', 'customer', 'date', 'due_date', 'total_amount', 'amount_received', 'status'], r
            )) for r in rows]}
            return pdf_response('receivables/invoice_list.html', ctx, 'sales-invoices')
        return xlsx_response(headers, rows, 'sales-invoices', 'Sales Invoices')

    @action(detail=True, methods=['post'], url_path='receive')
    def receive(self, request, pk=None):
        receipt_date = request.data.get('receipt_date')
        amount = request.data.get('amount')
        reference = request.data.get('reference', '')
        bank_account_id = request.data.get('bank_account_id')
        if not all([receipt_date, amount, bank_account_id]):
            return Response({'detail': 'receipt_date, amount, and bank_account_id are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'amount must be a valid number.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            receipt = services.record_receipt(
                pk, receipt_date, amount, reference, bank_account_id, request.user.username
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ARReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)
