from datetime import datetime
from django.utils import timezone

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import JournalEntry, Counter


def next_invoice_number(prefix: str, company_id: str) -> str:
    """PI-YYYY-XXXX / SI-YYYY-XXXX, sequence unique per company per year, via
    the shared race-safe Counter. Replaces the duplicated
    ORDER BY invoice_number DESC LIMIT 1 Cypher scan that used to live
    separately in payables/serializers.py and receivables/serializers.py.
    """
    year = datetime.now().year
    seq = Counter.next(f'{prefix}-{year}-{company_id}')
    return f'{prefix}-{year}-{seq:04d}'


@transaction.atomic
def post_entry(entry_id: str, company_id: str, approver) -> JournalEntry:
    entry = JournalEntry.objects.filter(entry_id=entry_id, company_id=company_id).select_for_update().first()
    if not entry:
        raise ValidationError('Journal entry not found.')
    if entry.status != 'DRAFT':
        raise ValidationError(f'Cannot post entry with status {entry.status}.')

    lines = list(entry.lines.select_related('account').all())
    if len(lines) < 2:
        raise ValidationError('Entry must have at least 2 lines.')

    total_debit = sum(l.amount for l in lines if l.side == 'DEBIT')
    total_credit = sum(l.amount for l in lines if l.side == 'CREDIT')
    if round(total_debit, 2) != round(total_credit, 2):
        raise ValidationError(f'Debits ({total_debit:.2f}) ≠ Credits ({total_credit:.2f}).')

    for line in lines:
        if not line.account or not line.account.is_active:
            raise ValidationError('Line references an inactive or missing account.')

    entry.status = 'POSTED'
    entry.approved_by = approver
    entry.approved_at = timezone.now()
    entry.save()
    return entry


def get_export_lines(company_id: str, date_from: str = None, date_to: str = None) -> list:
    """One row per JournalLine (not per entry) — each entry can post to several
    accounts (e.g. an AP invoice debits several expense accounts), so a
    per-entry summary can't show which account each amount actually hit.
    """
    from .models import JournalLine

    qs = JournalLine.objects.filter(entry__company_id=company_id).select_related('entry', 'account')
    if date_from:
        qs = qs.filter(entry__date__gte=date_from)
    if date_to:
        qs = qs.filter(entry__date__lte=date_to)
    qs = qs.order_by('-entry__date', '-entry__reference', 'side')

    rows = []
    for line in qs:
        amount = float(line.amount or 0)
        rows.append({
            'reference': line.entry.reference,
            'date': str(line.entry.date),
            'account': line.account.name if line.account else '',
            'description': line.description or line.entry.description,
            'debit': amount if line.side == 'DEBIT' else 0.0,
            'credit': amount if line.side == 'CREDIT' else 0.0,
            'status': line.entry.status,
        })
    return rows


@transaction.atomic
def void_entry(entry_id: str, company_id: str, voider) -> JournalEntry:
    entry = JournalEntry.objects.filter(entry_id=entry_id, company_id=company_id).select_for_update().first()
    if not entry:
        raise ValidationError('Journal entry not found.')
    if entry.status != 'POSTED':
        raise ValidationError(f'Only POSTED entries can be voided. Current status: {entry.status}.')

    entry.status = 'VOID'
    entry.voided_by = voider
    entry.voided_at = timezone.now()
    entry.save()
    return entry
