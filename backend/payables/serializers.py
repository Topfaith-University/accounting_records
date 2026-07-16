from rest_framework import serializers
from config.auth import get_active_company_id
from .models import Vendor, PurchaseInvoice, PurchaseInvoiceLine, APPayment, Item


def _next_invoice_number(prefix: str, label: str, company_id: str) -> str:
    from neomodel import db
    from datetime import datetime
    year = datetime.now().year
    pattern = f'{prefix}-{year}-'
    results, _ = db.cypher_query(
        f"MATCH (n:{label} {{company_id: $company_id}}) WHERE n.invoice_number STARTS WITH $pattern "
        f"RETURN n.invoice_number ORDER BY n.invoice_number DESC LIMIT 1",
        {'pattern': pattern, 'company_id': company_id}
    )
    if results and results[0][0]:
        try:
            num = int(results[0][0].split('-')[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f'{prefix}-{year}-{num:04d}'


class VendorSerializer(serializers.Serializer):
    vendor_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=200)
    email = serializers.CharField(default='', allow_blank=True)
    phone = serializers.CharField(default='', allow_blank=True)
    address = serializers.CharField(default='', allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    created_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])
        vendor = Vendor(company_id=company_id, **validated_data)
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
    quantity = serializers.FloatField(default=1.0, min_value=0.01)
    unit_price = serializers.FloatField(default=0.0, min_value=0)
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
    invoice_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
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
        if not self.partial and len(lines) < 1:
            raise serializers.ValidationError({'lines': 'At least one line is required.'})
        return data

    def create(self, validated_data):
        from accounts.models import Account
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', [])
        vendor_id = validated_data.pop('vendor_id')
        ap_account_id = validated_data.pop('ap_account_id')

        if not validated_data.get('invoice_number'):
            validated_data['invoice_number'] = _next_invoice_number('PI', 'PurchaseInvoice', company_id)

        invoice = PurchaseInvoice(company_id=company_id, **validated_data)
        invoice.save()

        vendor = Vendor.nodes.get_or_none(vendor_id=vendor_id, company_id=company_id)
        if vendor:
            invoice.vendor.connect(vendor)

        ap_acct = Account.nodes.get_or_none(account_id=ap_account_id, company_id=company_id)
        if ap_acct:
            invoice.ap_account.connect(ap_acct)

        for line_data in lines_data:
            expense_account_id = line_data.pop('expense_account_id')
            line = PurchaseInvoiceLine(company_id=company_id, **line_data)
            line.save()
            invoice.lines.connect(line)
            expense_acct = Account.nodes.get_or_none(account_id=expense_account_id, company_id=company_id)
            if expense_acct:
                line.expense_account.connect(expense_acct)

        return invoice

    def update(self, instance, validated_data):
        from accounts.models import Account
        company_id = get_active_company_id(self.context['request'])

        lines_data = validated_data.pop('lines', None)
        vendor_id = validated_data.pop('vendor_id', None)
        ap_account_id = validated_data.pop('ap_account_id', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if vendor_id:
            # vendor is cardinality=One — a saved invoice always has exactly one,
            # so this must go through reconnect(), not disconnect()+connect()
            # (disconnecting a cardinality=One relationship raises
            # AttemptedCardinalityViolation; only reconnect() is allowed).
            vendor = Vendor.nodes.get_or_none(vendor_id=vendor_id, company_id=company_id)
            if vendor:
                current_vendor = instance.vendor.single()
                if current_vendor:
                    instance.vendor.reconnect(current_vendor, vendor)
                else:
                    instance.vendor.connect(vendor)

        if ap_account_id:
            ap_account = Account.nodes.get_or_none(account_id=ap_account_id, company_id=company_id)
            if ap_account:
                current_ap_account = instance.ap_account.single()
                if current_ap_account:
                    instance.ap_account.reconnect(current_ap_account, ap_account)
                else:
                    instance.ap_account.connect(ap_account)

        if lines_data is not None:
            # existing_line.delete() is DETACH DELETE — it removes the line's
            # expense_account relationship (cardinality=One) automatically, so
            # there's nothing to disconnect first (disconnect() would raise
            # AttemptedCardinalityViolation on a cardinality=One relationship).
            for existing_line in list(instance.lines.all()):
                instance.lines.disconnect(existing_line)
                existing_line.delete()

            for line_data in lines_data:
                expense_account_id = line_data.pop('expense_account_id')
                line = PurchaseInvoiceLine(company_id=company_id, **line_data)
                line.save()
                instance.lines.connect(line)
                expense_account = Account.nodes.get_or_none(account_id=expense_account_id, company_id=company_id)
                if expense_account:
                    line.expense_account.connect(expense_account)

        return instance


class ItemSerializer(serializers.Serializer):
    item_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(default='', allow_blank=True)
    cost_price = serializers.FloatField(default=0.0, min_value=0)
    selling_price = serializers.FloatField(default=0.0, min_value=0)
    item_type = serializers.ChoiceField(choices=['PRODUCT', 'SERVICE'], default='SERVICE')
    is_active = serializers.BooleanField(default=True)
    created_at = serializers.DateTimeField(read_only=True)

    vendor_id = serializers.CharField(write_only=True, allow_null=True, allow_blank=True, required=False)
    expense_account_id = serializers.CharField(write_only=True, allow_null=True, allow_blank=True, required=False)
    revenue_account_id = serializers.CharField(write_only=True, allow_null=True, allow_blank=True, required=False)

    vendor_name = serializers.SerializerMethodField()
    expense_account_label = serializers.SerializerMethodField()
    revenue_account_label = serializers.SerializerMethodField()

    def get_vendor_name(self, obj):
        try:
            v = obj.vendor.single()
            return v.name if v else None
        except Exception:
            return None

    def get_expense_account_label(self, obj):
        try:
            a = obj.expense_account.single()
            return f'{a.code} — {a.name}' if a else None
        except Exception:
            return None

    def get_revenue_account_label(self, obj):
        try:
            a = obj.revenue_account.single()
            return f'{a.code} — {a.name}' if a else None
        except Exception:
            return None

    def _connect_relations(self, instance, vendor_id, expense_account_id, revenue_account_id):
        from accounts.models import Account
        company_id = get_active_company_id(self.context['request'])
        if vendor_id is not None:
            current = instance.vendor.single()
            if current:
                instance.vendor.disconnect(current)
            if vendor_id:
                vendor = Vendor.nodes.get_or_none(vendor_id=vendor_id, company_id=company_id)
                if vendor:
                    instance.vendor.connect(vendor)
        if expense_account_id is not None:
            current = instance.expense_account.single()
            if current:
                instance.expense_account.disconnect(current)
            if expense_account_id:
                acct = Account.nodes.get_or_none(account_id=expense_account_id, company_id=company_id)
                if acct:
                    instance.expense_account.connect(acct)
        if revenue_account_id is not None:
            current = instance.revenue_account.single()
            if current:
                instance.revenue_account.disconnect(current)
            if revenue_account_id:
                acct = Account.nodes.get_or_none(account_id=revenue_account_id, company_id=company_id)
                if acct:
                    instance.revenue_account.connect(acct)

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])
        vendor_id = validated_data.pop('vendor_id', None)
        expense_account_id = validated_data.pop('expense_account_id', None)
        revenue_account_id = validated_data.pop('revenue_account_id', None)
        item = Item(company_id=company_id, **validated_data)
        item.save()
        self._connect_relations(item, vendor_id, expense_account_id, revenue_account_id)
        return item

    def update(self, instance, validated_data):
        vendor_id_present = 'vendor_id' in validated_data
        expense_account_id_present = 'expense_account_id' in validated_data
        revenue_account_id_present = 'revenue_account_id' in validated_data

        vendor_id = validated_data.pop('vendor_id', None)
        expense_account_id = validated_data.pop('expense_account_id', None)
        revenue_account_id = validated_data.pop('revenue_account_id', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        self._connect_relations(
            instance,
            vendor_id if vendor_id_present else None,
            expense_account_id if expense_account_id_present else None,
            revenue_account_id if revenue_account_id_present else None,
        )
        return instance


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
