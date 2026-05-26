from rest_framework import serializers
from .models import Customer, SalesInvoice, SalesInvoiceLine, ARReceipt


def _next_invoice_number(prefix: str, label: str) -> str:
    from neomodel import db
    from datetime import datetime
    year = datetime.now().year
    pattern = f'{prefix}-{year}-'
    results, _ = db.cypher_query(
        f"MATCH (n:{label}) WHERE n.invoice_number STARTS WITH $pattern "
        f"RETURN n.invoice_number ORDER BY n.invoice_number DESC LIMIT 1",
        {'pattern': pattern}
    )
    if results and results[0][0]:
        try:
            num = int(results[0][0].split('-')[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f'{prefix}-{year}-{num:04d}'


class CustomerSerializer(serializers.Serializer):
    customer_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=200)
    email = serializers.CharField(default='', allow_blank=True)
    phone = serializers.CharField(default='', allow_blank=True)
    address = serializers.CharField(default='', allow_blank=True)
    customer_type = serializers.ChoiceField(choices=['STUDENT', 'EXTERNAL'], default='EXTERNAL')
    is_active = serializers.BooleanField(default=True)
    created_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        customer = Customer(**validated_data)
        customer.save()
        return customer

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class SalesInvoiceLineSerializer(serializers.Serializer):
    line_id = serializers.CharField(read_only=True)
    description = serializers.CharField(default='', allow_blank=True)
    amount = serializers.FloatField(min_value=0.01)
    revenue_account_id = serializers.CharField(write_only=True)
    revenue_account_code = serializers.SerializerMethodField()
    revenue_account_name = serializers.SerializerMethodField()

    def get_revenue_account_code(self, obj):
        try:
            acct = obj.revenue_account.single()
            return acct.code if acct else None
        except Exception:
            return None

    def get_revenue_account_name(self, obj):
        try:
            acct = obj.revenue_account.single()
            return acct.name if acct else None
        except Exception:
            return None


class SalesInvoiceSerializer(serializers.Serializer):
    invoice_id = serializers.CharField(read_only=True)
    invoice_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
    date = serializers.DateField()
    due_date = serializers.DateField()
    description = serializers.CharField(default='', allow_blank=True)
    status = serializers.CharField(read_only=True)
    total_amount = serializers.FloatField(read_only=True)
    amount_received = serializers.FloatField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    customer_id = serializers.CharField(write_only=True)
    ar_account_id = serializers.CharField(write_only=True)
    customer_name = serializers.SerializerMethodField()
    ar_account_label = serializers.SerializerMethodField()
    lines = SalesInvoiceLineSerializer(many=True, required=False)

    def get_customer_name(self, obj):
        try:
            c = obj.customer.single()
            return c.name if c else None
        except Exception:
            return None

    def get_ar_account_label(self, obj):
        try:
            a = obj.ar_account.single()
            return f'{a.code} — {a.name}' if a else None
        except Exception:
            return None

    def validate(self, data):
        lines = data.get('lines', [])
        if not self.partial and len(lines) < 1:
            raise serializers.ValidationError({'lines': 'At least one line is required.'})
        return data

    def create(self, validated_data):
        from accounts.models import Account
        lines_data = validated_data.pop('lines', [])
        customer_id = validated_data.pop('customer_id')
        ar_account_id = validated_data.pop('ar_account_id')

        if not validated_data.get('invoice_number'):
            validated_data['invoice_number'] = _next_invoice_number('SI', 'SalesInvoice')

        invoice = SalesInvoice(**validated_data)
        invoice.save()

        customer = Customer.nodes.get_or_none(customer_id=customer_id)
        if customer:
            invoice.customer.connect(customer)

        ar_acct = Account.nodes.get_or_none(account_id=ar_account_id)
        if ar_acct:
            invoice.ar_account.connect(ar_acct)

        for line_data in lines_data:
            revenue_account_id = line_data.pop('revenue_account_id')
            line = SalesInvoiceLine(**line_data)
            line.save()
            invoice.lines.connect(line)
            revenue_acct = Account.nodes.get_or_none(account_id=revenue_account_id)
            if revenue_acct:
                line.revenue_account.connect(revenue_acct)

        return invoice

    def update(self, instance, validated_data):
        from accounts.models import Account

        lines_data = validated_data.pop('lines', None)
        customer_id = validated_data.pop('customer_id', None)
        ar_account_id = validated_data.pop('ar_account_id', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if customer_id:
            current_customer = instance.customer.single()
            if current_customer:
                instance.customer.disconnect(current_customer)
            customer = Customer.nodes.get_or_none(customer_id=customer_id)
            if customer:
                instance.customer.connect(customer)

        if ar_account_id:
            current_ar_account = instance.ar_account.single()
            if current_ar_account:
                instance.ar_account.disconnect(current_ar_account)
            ar_account = Account.nodes.get_or_none(account_id=ar_account_id)
            if ar_account:
                instance.ar_account.connect(ar_account)

        if lines_data is not None:
            for existing_line in list(instance.lines.all()):
                instance.lines.disconnect(existing_line)
                revenue_account = existing_line.revenue_account.single()
                if revenue_account:
                    existing_line.revenue_account.disconnect(revenue_account)
                existing_line.delete()

            for line_data in lines_data:
                revenue_account_id = line_data.pop('revenue_account_id')
                line = SalesInvoiceLine(**line_data)
                line.save()
                instance.lines.connect(line)
                revenue_account = Account.nodes.get_or_none(account_id=revenue_account_id)
                if revenue_account:
                    line.revenue_account.connect(revenue_account)

        return instance


class ARReceiptSerializer(serializers.Serializer):
    receipt_id = serializers.CharField(read_only=True)
    receipt_date = serializers.DateField(read_only=True)
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
