from django.conf import settings
from django.db import models

from config.ids import new_id
from users.models import Company
from accounts.models import Account
from journals.models import JournalLine, JournalEntry


class BankAccount(models.Model):
    bank_account_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='bank_accounts')
    name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50, blank=True, default='')
    bank_name = models.CharField(max_length=200)
    currency = models.CharField(max_length=10, default='NGN')
    opening_balance = models.FloatField(default=0.0)
    opening_balance_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    # Nullable: a bank account can be created before its GL account is linked
    # (create_bank_transaction is what actually enforces this is set).
    gl_account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.PROTECT, related_name='bank_accounts',
    )


class BankReconciliation(models.Model):
    reconciliation_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='bank_reconciliations')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='reconciliations')
    period_start = models.DateField()
    period_end = models.DateField()
    statement_balance = models.FloatField()
    status = models.CharField(
        max_length=9, choices=[('DRAFT', 'Draft'), ('COMPLETED', 'Completed')], default='DRAFT',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reconciled_lines = models.ManyToManyField(JournalLine, related_name='reconciliations', blank=True)


class BankTransaction(models.Model):
    transaction_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='bank_transactions')
    reference = models.CharField(max_length=50)
    transaction_type = models.CharField(
        max_length=8,
        choices=[('RECEIPT', 'Receipt'), ('PAYMENT', 'Payment'), ('TRANSFER', 'Transfer')],
    )
    date = models.DateField()
    amount = models.FloatField()
    description = models.TextField(default='', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    source_bank = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='outgoing_transactions',
    )
    destination_bank = models.ForeignKey(
        BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='incoming_transactions',
    )
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.PROTECT, related_name='bank_transactions',
    )
    vendor = models.ForeignKey(
        'payables.Vendor', null=True, blank=True, on_delete=models.SET_NULL, related_name='bank_transactions',
    )
    customer = models.ForeignKey(
        'receivables.Customer', null=True, blank=True, on_delete=models.SET_NULL, related_name='bank_transactions',
    )

    class Meta:
        unique_together = [('company', 'reference')]
