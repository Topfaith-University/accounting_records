from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Customer, SalesInvoice, ARReceipt
from .serializers import CustomerSerializer, SalesInvoiceSerializer, ARReceiptSerializer
from . import services


def _serialize_invoice(invoice):
    data = SalesInvoiceSerializer(invoice).data
    lines = list(invoice.lines.all())
    from .serializers import SalesInvoiceLineSerializer
    data['lines'] = SalesInvoiceLineSerializer(lines, many=True).data
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


class SalesInvoiceViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        invoices = SalesInvoice.nodes.all()
        inv_status = request.query_params.get('status')
        if inv_status:
            invoices = [i for i in invoices if i.status == inv_status.upper()]
        else:
            invoices = list(invoices)
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
            receipt = services.record_receipt(
                pk, receipt_date, float(amount), reference, bank_account_id, request.user.username
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ARReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)
