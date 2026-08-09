from rest_framework import serializers
from config.auth import get_active_company_id
from accounts.models import Account
from .models import Customer, SalesInvoice, SalesInvoiceLine, ARReceipt


class CustomerSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'customer_id', 'name', 'email', 'phone', 'address', 'customer_type',
            'is_active', 'balance', 'created_at',
        ]
        read_only_fields = ['customer_id', 'created_at']

    def get_balance(self, obj):
        total = sum(
            max(0.0, inv.total_amount - inv.amount_received)
            for inv in obj.invoices.filter(status__in=('POSTED', 'PAID'))
        )
        return round(total, 2)

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])
        return Customer.objects.create(company_id=company_id, **validated_data)


class SalesInvoiceLineSerializer(serializers.ModelSerializer):
    revenue_account_id = serializers.PrimaryKeyRelatedField(source='revenue_account', queryset=Account.objects.all())
    revenue_account_code = serializers.CharField(source='revenue_account.code', read_only=True)
    revenue_account_name = serializers.CharField(source='revenue_account.name', read_only=True)

    class Meta:
        model = SalesInvoiceLine
        fields = [
            'line_id', 'description', 'quantity', 'unit_price', 'amount',
            'revenue_account_id', 'revenue_account_code', 'revenue_account_name',
        ]
        read_only_fields = ['line_id']
        extra_kwargs = {
            'quantity': {'min_value': 0.01},
            'unit_price': {'min_value': 0},
            'amount': {'min_value': 0.01},
        }


class SalesInvoiceSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    customer_id = serializers.PrimaryKeyRelatedField(source='customer', queryset=Customer.objects.all())
    ar_account_id = serializers.PrimaryKeyRelatedField(source='ar_account', queryset=Account.objects.all())
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    ar_account_label = serializers.SerializerMethodField()
    lines = SalesInvoiceLineSerializer(many=True, required=False)

    class Meta:
        model = SalesInvoice
        fields = [
            'invoice_id', 'invoice_number', 'date', 'due_date', 'description', 'status',
            'total_amount', 'amount_received', 'created_by', 'created_at',
            'customer_id', 'ar_account_id', 'customer_name', 'ar_account_label', 'lines',
        ]
        read_only_fields = ['invoice_id', 'status', 'total_amount', 'amount_received', 'created_at']

    def get_ar_account_label(self, obj):
        return f'{obj.ar_account.code} — {obj.ar_account.name}' if obj.ar_account_id else None

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
            validated_data['invoice_number'] = next_invoice_number('SI', company_id)

        invoice = SalesInvoice.objects.create(company_id=company_id, **validated_data)
        for line_data in lines_data:
            SalesInvoiceLine.objects.create(company_id=company_id, invoice=invoice, **line_data)
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
                SalesInvoiceLine.objects.create(company_id=company_id, invoice=instance, **line_data)

        return instance


class ARReceiptSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    invoice_id = serializers.PrimaryKeyRelatedField(source='invoice', read_only=True)

    class Meta:
        model = ARReceipt
        fields = ['receipt_id', 'receipt_date', 'amount', 'reference', 'created_by', 'created_at', 'invoice_id']
        read_only_fields = ['receipt_id', 'receipt_date', 'amount', 'reference', 'created_at']
