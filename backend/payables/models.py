from django.conf import settings
from django.db import models

from config.ids import new_id
from users.models import Company
from accounts.models import Account
from journals.models import JournalEntry


class Vendor(models.Model):
    vendor_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='vendors')
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=200, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    address = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PurchaseInvoice(models.Model):
    invoice_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='purchase_invoices')
    invoice_number = models.CharField(max_length=50)
    date = models.DateField()
    due_date = models.DateField()
    description = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=6,
        choices=[('DRAFT', 'Draft'), ('POSTED', 'Posted'), ('PAID', 'Paid'), ('VOID', 'Void')],
        default='DRAFT',
    )
    total_amount = models.FloatField(default=0.0)
    amount_paid = models.FloatField(default=0.0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='invoices')
    ap_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='payable_invoices')
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='purchase_invoices',
    )


class PurchaseInvoiceLine(models.Model):
    line_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='purchase_invoice_lines')
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='lines')
    description = models.TextField(blank=True, default='')
    quantity = models.FloatField(default=1.0)
    unit_price = models.FloatField(default=0.0)
    amount = models.FloatField()
    expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='purchase_invoice_lines',
    )


class Item(models.Model):
    item_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    cost_price = models.FloatField(default=0.0)
    selling_price = models.FloatField(default=0.0)
    item_type = models.CharField(
        max_length=7, choices=[('PRODUCT', 'Product'), ('SERVICE', 'Service')], default='SERVICE',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    vendor = models.ForeignKey(
        Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name='items',
    )
    expense_account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name='default_expense_items',
    )
    revenue_account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name='default_revenue_items',
    )


class APPayment(models.Model):
    payment_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='ap_payments')
    payment_date = models.DateField()
    amount = models.FloatField()
    reference = models.CharField(max_length=100, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.PROTECT, related_name='payments')
    bank_account = models.ForeignKey('banks.BankAccount', on_delete=models.PROTECT, related_name='ap_payments')
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='ap_payments',
    )
