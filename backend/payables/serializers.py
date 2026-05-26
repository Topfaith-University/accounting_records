from rest_framework import serializers
from .models import Vendor, PurchaseInvoice, PurchaseInvoiceLine, APPayment


class VendorSerializer(serializers.Serializer):
    vendor_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=200)
    email = serializers.CharField(default='', allow_blank=True)
    phone = serializers.CharField(default='', allow_blank=True)
    address = serializers.CharField(default='', allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    created_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        vendor = Vendor(**validated_data)
        vendor.save()
        return vendor

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class PurchaseInvoiceLineSerializer(serializers.Serializer):
    line_id = serializers.CharField(read_only=True)
    description = serializers.CharField(default='', allow_blank=True)
    amount = serializers.FloatField(min_value=0.01)
    expense_account_id = serializers.CharField(write_only=True)
    expense_account_code = serializers.SerializerMethodField()
    expense_account_name = serializers.SerializerMethodField()

    def get_expense_account_code(self, obj):
        try:
            acct = obj.expense_account.single()
            return acct.code if acct else None
        except Exception:
            return None

    def get_expense_account_name(self, obj):
        try:
            acct = obj.expense_account.single()
            return acct.name if acct else None
        except Exception:
            return None


class PurchaseInvoiceSerializer(serializers.Serializer):
    invoice_id = serializers.CharField(read_only=True)
    invoice_number = serializers.CharField(max_length=50)
    date = serializers.DateField()
    due_date = serializers.DateField()
    description = serializers.CharField(default='', allow_blank=True)
    status = serializers.CharField(read_only=True)
    total_amount = serializers.FloatField(read_only=True)
    amount_paid = serializers.FloatField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    vendor_id = serializers.CharField(write_only=True)
    ap_account_id = serializers.CharField(write_only=True)
    vendor_name = serializers.SerializerMethodField()
    ap_account_label = serializers.SerializerMethodField()
    lines = PurchaseInvoiceLineSerializer(many=True, required=False)

    def get_vendor_name(self, obj):
        try:
            v = obj.vendor.single()
            return v.name if v else None
        except Exception:
            return None

    def get_ap_account_label(self, obj):
        try:
            a = obj.ap_account.single()
            return f'{a.code} — {a.name}' if a else None
        except Exception:
            return None

    def validate(self, data):
        lines = data.get('lines', [])
        if len(lines) < 1:
            raise serializers.ValidationError({'lines': 'At least one line is required.'})
        return data

    def create(self, validated_data):
        from accounts.models import Account
        lines_data = validated_data.pop('lines', [])
        vendor_id = validated_data.pop('vendor_id')
        ap_account_id = validated_data.pop('ap_account_id')

        invoice = PurchaseInvoice(**validated_data)
        invoice.save()

        vendor = Vendor.nodes.get_or_none(vendor_id=vendor_id)
        if vendor:
            invoice.vendor.connect(vendor)

        ap_acct = Account.nodes.get_or_none(account_id=ap_account_id)
        if ap_acct:
            invoice.ap_account.connect(ap_acct)

        for line_data in lines_data:
            expense_account_id = line_data.pop('expense_account_id')
            line = PurchaseInvoiceLine(**line_data)
            line.save()
            invoice.lines.connect(line)
            expense_acct = Account.nodes.get_or_none(account_id=expense_account_id)
            if expense_acct:
                line.expense_account.connect(expense_acct)

        return invoice


class APPaymentSerializer(serializers.Serializer):
    payment_id = serializers.CharField(read_only=True)
    payment_date = serializers.DateField()
    amount = serializers.FloatField(read_only=True)
    reference = serializers.CharField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    invoice_id = serializers.SerializerMethodField()

    def get_invoice_id(self, obj):
        try:
            inv = obj.invoice.single()
            return inv.invoice_id if inv else None
        except Exception:
            return None
