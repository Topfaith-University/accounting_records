from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.export_utils import pdf_response
from config.auth import get_active_company_id
from .models import Customer, SalesInvoice
from .serializers import CustomerSerializer, SalesInvoiceSerializer, ARReceiptSerializer, SalesInvoiceLineSerializer
from . import services


class CustomerViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        customers = Customer.objects.filter(company_id=company_id, is_active=True)
        return Response(CustomerSerializer(customers, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        customer = Customer.objects.filter(customer_id=pk, company_id=company_id).first()
        if not customer:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CustomerSerializer(customer).data)

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = CustomerSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        customer = Customer.objects.filter(customer_id=pk, company_id=company_id).first()
        if not customer:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CustomerSerializer(customer, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(CustomerSerializer(customer).data)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        customer = Customer.objects.filter(customer_id=pk, company_id=company_id).first()
        if not customer:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        customer.is_active = False
        customer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='statement')
    def statement(self, request, pk=None):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        data = services.get_customer_statement(pk, company_id)
        if data is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        fmt = request.query_params.get('format', 'json')
        if fmt == 'pdf':
            return pdf_response(request, 'receivables/customer_statement.html', data, f'customer-statement-{pk}')
        if fmt == 'xlsx':
            headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)']
            rows = [
                [l['date'], l['type'], l['reference'], l['description'], l['debit'], l['credit'], l['running_balance']]
                for l in data['lines']
            ]
            rows.append(['', '', '', '', '', 'CLOSING BALANCE', data['closing_balance']])
            return xlsx_response(request, headers, rows, f'customer-statement-{pk}', 'Statement')
        return Response(data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        customers = Customer.objects.filter(company_id=company_id, is_active=True).order_by('name')
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Name', 'Type', 'Email', 'Phone']
        rows = [[c.name, c.customer_type, c.email, c.phone] for c in customers]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['name', 'customer_type', 'email', 'phone'], r)) for r in rows]}
            return pdf_response(request, 'receivables/customer_list.html', ctx, 'customers')
        return xlsx_response(request, headers, rows, 'customers', 'Customers')


class SalesInvoiceViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        invoices = SalesInvoice.objects.filter(company_id=company_id).select_related('customer', 'ar_account')
        inv_status = request.query_params.get('status')
        if inv_status:
            invoices = invoices.filter(status=inv_status.upper())
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            invoices = invoices.filter(customer_id=customer_id)
        invoices = invoices.order_by('-date')
        return Response(SalesInvoiceSerializer(invoices, many=True).data)

    def retrieve(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = SalesInvoice.objects.filter(invoice_id=pk, company_id=company_id).select_related('customer', 'ar_account').first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(SalesInvoiceSerializer(invoice).data)

    @action(detail=True, methods=['get'], url_path='print')
    def print_invoice(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = SalesInvoice.objects.filter(invoice_id=pk, company_id=company_id).select_related('customer').first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        lines = list(invoice.lines.select_related('revenue_account').all())
        return pdf_response(request, 'receivables/sales_invoice.html', {
            'invoice': invoice,
            'customer': invoice.customer,
            'lines': lines,
            'settled_amount': invoice.amount_received,
            'outstanding_amount': max(0, invoice.total_amount - invoice.amount_received),
        }, f'sales-invoice-{invoice.invoice_number}')

    def create(self, request):
        if not get_active_company_id(request):
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = SalesInvoiceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save(created_by=request.user)
        return Response(SalesInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = SalesInvoice.objects.filter(invoice_id=pk, company_id=company_id).first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = SalesInvoiceSerializer(invoice, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        return Response(SalesInvoiceSerializer(invoice).data)

    def destroy(self, request, pk=None):
        company_id = get_active_company_id(request)
        invoice = SalesInvoice.objects.filter(invoice_id=pk, company_id=company_id).first()
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        invoice.delete()  # SalesInvoiceLine.invoice FK is on_delete=CASCADE
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='post')
    def post_invoice(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            invoice = services.post_invoice(pk, company_id, request.user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesInvoiceSerializer(invoice).data)

    @action(detail=True, methods=['post'], url_path='void')
    def void_invoice(self, request, pk=None):
        company_id = get_active_company_id(request)
        try:
            invoice = services.void_invoice(pk, company_id, request.user)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesInvoiceSerializer(invoice).data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        invoices = SalesInvoice.objects.filter(company_id=company_id).select_related('customer').order_by('-date')
        fmt = request.query_params.get('format', 'xlsx')
        headers = ['Invoice #', 'Customer', 'Date', 'Due Date', 'Total (N)', 'Received (N)', 'Status']
        rows = [
            [
                inv.invoice_number, inv.customer.name if inv.customer else '', str(inv.date), str(inv.due_date),
                inv.total_amount, inv.amount_received, inv.status,
            ]
            for inv in invoices
        ]
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['invoice_number', 'customer', 'date', 'due_date', 'total_amount', 'amount_received', 'status'], r
            )) for r in rows]}
            return pdf_response(request, 'receivables/invoice_list.html', ctx, 'sales-invoices')
        return xlsx_response(request, headers, rows, 'sales-invoices', 'Sales Invoices')

    @action(detail=True, methods=['post'], url_path='receive')
    def receive(self, request, pk=None):
        company_id = get_active_company_id(request)
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
                pk, company_id, receipt_date, amount, reference, bank_account_id, request.user
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ARReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)
