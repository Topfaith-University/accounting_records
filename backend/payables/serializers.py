from rest_framework import serializers
from config.auth import get_active_company_id
from accounts.models import Account
from .models import Vendor, PurchaseInvoice, PurchaseInvoiceLine, APPayment, Item


class VendorSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ['vendor_id', 'name', 'email', 'phone', 'address', 'is_active', 'balance', 'created_at']
        read_only_fields = ['vendor_id', 'created_at']

    def get_balance(self, obj):
        total = sum(
            max(0.0, inv.total_amount - inv.amount_paid)
            for inv in obj.invoices.filter(status__in=('POSTED', 'PAID'))
        )
        return round(total, 2)

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])
        return Vendor.objects.create(company_id=company_id, **validated_data)


class PurchaseInvoiceLineSerializer(serializers.ModelSerializer):
    expense_account_id = serializers.PrimaryKeyRelatedField(source='expense_account', queryset=Account.objects.all())
    expense_account_code = serializers.CharField(source='expense_account.code', read_only=True)
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True)

    class Meta:
        model = PurchaseInvoiceLine
        fields = [
            'line_id', 'description', 'quantity', 'unit_price', 'amount',
            'expense_account_id', 'expense_account_code', 'expense_account_name',
        ]
        read_only_fields = ['line_id']
        extra_kwargs = {
            'quantity': {'min_value': 0.01},
            'unit_price': {'min_value': 0},
            'amount': {'min_value': 0.01},
        }


class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    vendor_id = serializers.PrimaryKeyRelatedField(source='vendor', queryset=Vendor.objects.all())
    ap_account_id = serializers.PrimaryKeyRelatedField(source='ap_account', queryset=Account.objects.all())
    vendor_name = serializers.CharField(source='vendor.name', read_only=True, default=None)
    ap_account_label = serializers.SerializerMethodField()
    lines = PurchaseInvoiceLineSerializer(many=True, required=False)

    class Meta:
        model = PurchaseInvoice
        fields = [
            'invoice_id', 'invoice_number', 'date', 'due_date', 'description', 'status',
            'total_amount', 'amount_paid', 'created_by', 'created_at',
            'vendor_id', 'ap_account_id', 'vendor_name', 'ap_account_label', 'lines',
        ]
        read_only_fields = ['invoice_id', 'status', 'total_amount', 'amount_paid', 'created_at']

    def get_ap_account_label(self, obj):
        return f'{obj.ap_account.code} — {obj.ap_account.name}' if obj.ap_account_id else None

    def validate(self, data):
        lines = data.get('lines', [])
        if not self.partial and len(lines) < 1:
            raise serializers.ValidationError({'lines': 'At least one line is required.'})
        return data

    def create(self, validated_data):
        from journals.services import next_invoice_number
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', [])

        if not validated_data.get('invoice_number'):
            validated_data['invoice_number'] = next_invoice_number('PI', company_id)

        invoice = PurchaseInvoice.objects.create(company_id=company_id, **validated_data)
        for line_data in lines_data:
            PurchaseInvoiceLine.objects.create(company_id=company_id, invoice=invoice, **line_data)
        return invoice

    def update(self, instance, validated_data):
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                PurchaseInvoiceLine.objects.create(company_id=company_id, invoice=instance, **line_data)

        return instance


class ItemSerializer(serializers.ModelSerializer):
    vendor_id = serializers.PrimaryKeyRelatedField(
        source='vendor', queryset=Vendor.objects.all(), required=False, allow_null=True,
    )
    expense_account_id = serializers.PrimaryKeyRelatedField(
        source='expense_account', queryset=Account.objects.all(), required=False, allow_null=True,
    )
    revenue_account_id = serializers.PrimaryKeyRelatedField(
        source='revenue_account', queryset=Account.objects.all(), required=False, allow_null=True,
    )
    vendor_name = serializers.CharField(source='vendor.name', read_only=True, default=None)
    expense_account_label = serializers.SerializerMethodField()
    revenue_account_label = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'item_id', 'name', 'description', 'cost_price', 'selling_price', 'item_type', 'is_active',
            'vendor_id', 'expense_account_id', 'revenue_account_id',
            'vendor_name', 'expense_account_label', 'revenue_account_label', 'created_at',
        ]
        read_only_fields = ['item_id', 'created_at']

    def get_expense_account_label(self, obj):
        return f'{obj.expense_account.code} — {obj.expense_account.name}' if obj.expense_account_id else None

    def get_revenue_account_label(self, obj):
        return f'{obj.revenue_account.code} — {obj.revenue_account.name}' if obj.revenue_account_id else None

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])
        return Item.objects.create(company_id=company_id, **validated_data)


class APPaymentSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    invoice_id = serializers.PrimaryKeyRelatedField(source='invoice', read_only=True)

    class Meta:
        model = APPayment
        fields = ['payment_id', 'payment_date', 'amount', 'reference', 'created_by', 'created_at', 'invoice_id']
        read_only_fields = ['payment_id', 'amount', 'reference', 'created_at']
