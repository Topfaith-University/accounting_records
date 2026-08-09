from django.conf import settings
from django.db import models, transaction

from config.ids import new_id
from users.models import Company
from accounts.models import Account


class FiscalYear(models.Model):
    year_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='fiscal_years')
    name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=6, choices=[('OPEN', 'Open'), ('CLOSED', 'Closed')], default='OPEN',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class AccountingPeriod(models.Model):
    period_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='accounting_periods')
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name='periods')
    name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    period_number = models.IntegerField()
    status = models.CharField(
        max_length=6, choices=[('OPEN', 'Open'), ('CLOSED', 'Closed')], default='OPEN',
    )


class JournalEntry(models.Model):
    ENTRY_TYPES = [
        ('MANUAL', 'Manual'),
        ('BANK_RECON', 'Bank Reconciliation'),
        ('AP_PAYMENT', 'AP Payment'),
        ('AR_RECEIPT', 'AR Receipt'),
        ('BANK_TRANSACTION', 'Bank Transaction'),
    ]

    entry_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='journal_entries')
    reference = models.CharField(max_length=50)
    date = models.DateField()
    description = models.CharField(max_length=500)
    status = models.CharField(
        max_length=6,
        choices=[('DRAFT', 'Draft'), ('POSTED', 'Posted'), ('VOID', 'Void')],
        default='DRAFT',
    )
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='MANUAL')
    total_debit = models.FloatField(default=0.0)
    total_credit = models.FloatField(default=0.0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    period = models.ForeignKey(
        AccountingPeriod, null=True, blank=True, on_delete=models.SET_NULL, related_name='entries',
    )

    class Meta:
        unique_together = [('company', 'reference')]
        verbose_name_plural = 'journal entries'


class JournalLine(models.Model):
    line_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='journal_lines')
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    side = models.CharField(max_length=6, choices=[('DEBIT', 'Debit'), ('CREDIT', 'Credit')])
    amount = models.FloatField()
    description = models.TextField(default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Counter(models.Model):
    """Race-safe sequence generator. Replaces neomodel's per-app MERGE-based
    counters (BankTxnCounter, InvoiceSettlementCounter) and the duplicated
    ORDER BY reference DESC LIMIT 1 invoice-numbering logic that used to live
    separately in payables/serializers.py and receivables/serializers.py.
    """
    key = models.CharField(max_length=200, unique=True)
    seq = models.PositiveIntegerField(default=0)

    @classmethod
    def next(cls, key: str) -> int:
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(key=key)
            counter.seq = models.F('seq') + 1
            counter.save(update_fields=['seq'])
            counter.refresh_from_db(fields=['seq'])
            return counter.seq
