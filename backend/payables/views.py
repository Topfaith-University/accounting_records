from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Vendor, PurchaseInvoice, APPayment
from .serializers import VendorSerializer, PurchaseInvoiceSerializer, APPaymentSerializer
from . import services


def _serialize_invoice(invoice):
    data = PurchaseInvoiceSerializer(invoice).data
    lines = list(invoice.lines.all())
    from .serializers import PurchaseInvoiceLineSerializer
    data['lines'] = PurchaseInvoiceLineSerializer(lines, many=True).data
    return data


class VendorViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        vendors = [v for v in Vendor.nodes.all() if v.is_active]
        return Response(VendorSerializer(vendors, many=True).data)

    def retrieve(self, request, pk=None):
        vendor = Vendor.nodes.get_or_none(vendor_id=pk)
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(VendorSerializer(vendor).data)

    def create(self, request):
        serializer = VendorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(VendorSerializer(vendor).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        vendor = Vendor.nodes.get_or_none(vendor_id=pk)
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = VendorSerializer(vendor, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(VendorSerializer(vendor).data)


class PurchaseInvoiceViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        invoices = PurchaseInvoice.nodes.all()
        inv_status = request.query_params.get('status')
        if inv_status:
            invoices = [i for i in invoices if i.status == inv_status.upper()]
        else:
            invoices = list(invoices)
        invoices = sorted(invoices, key=lambda i: str(i.date), reverse=True)
        return Response(PurchaseInvoiceSerializer(invoices, many=True).data)

    def retrieve(self, request, pk=None):
        invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize_invoice(invoice))

    def create(self, request):
        serializer = PurchaseInvoiceSerializer(data=request.data)
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

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        payment_date = request.data.get('payment_date')
        amount = request.data.get('amount')
        reference = request.data.get('reference', '')
        bank_account_id = request.data.get('bank_account_id')
        if not all([payment_date, amount, bank_account_id]):
            return Response({'detail': 'payment_date, amount, and bank_account_id are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            payment = services.record_payment(
                pk, payment_date, float(amount), reference, bank_account_id, request.user.username
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(APPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
