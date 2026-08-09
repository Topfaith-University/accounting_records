from django.conf import settings
from django.db import models

from config.ids import new_id
from users.models import Company
from accounts.models import Account
from journals.models import JournalEntry


class Customer(models.Model):
    customer_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='customers')
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=200, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    address = models.TextField(blank=True, default='')
    customer_type = models.CharField(
        max_length=8, choices=[('STUDENT', 'Student'), ('EXTERNAL', 'External')], default='EXTERNAL',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SalesInvoice(models.Model):
    invoice_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='sales_invoices')
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
    amount_received = models.FloatField(default=0.0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    ar_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='receivable_invoices')
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='sales_invoices',
    )


class SalesInvoiceLine(models.Model):
    line_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='sales_invoice_lines')
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='lines')
    description = models.TextField(blank=True, default='')
    quantity = models.FloatField(default=1.0)
    unit_price = models.FloatField(default=0.0)
    amount = models.FloatField()
    revenue_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='sales_invoice_lines',
    )


class ARReceipt(models.Model):
    receipt_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='ar_receipts')
    receipt_date = models.DateField()
    amount = models.FloatField()
    reference = models.CharField(max_length=100, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name='receipts')
    bank_account = models.ForeignKey('banks.BankAccount', on_delete=models.PROTECT, related_name='ar_receipts')
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='ar_receipts',
    )
