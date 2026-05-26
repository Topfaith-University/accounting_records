from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Vendor, PurchaseInvoice, APPayment
from .serializers import VendorSerializer, PurchaseInvoiceSerializer, APPaymentSerializer, PurchaseInvoiceLineSerializer
from . import services


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

    def destroy(self, request, pk=None):
        vendor = Vendor.nodes.get_or_none(vendor_id=pk)
        if not vendor:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        vendor.is_active = False
        vendor.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


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

    def partial_update(self, request, pk=None):
        invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk)
        if not invoice:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != 'DRAFT':
            return Response({'detail': 'Only draft invoices can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseInvoiceSerializer(invoice, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        return Response(_serialize_invoice(invoice))

    def destroy(self, request, pk=None):
        invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk)
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
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'amount must be a valid number.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payment = services.record_payment(
                pk, payment_date, amount, reference, bank_account_id, request.user.username
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(APPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
