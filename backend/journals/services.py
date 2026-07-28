from rest_framework.exceptions import ValidationError
from .models import JournalEntry


def post_entry(entry_id: str, company_id: str, approver_username: str) -> JournalEntry:
    entry = JournalEntry.nodes.get_or_none(entry_id=entry_id, company_id=company_id)
    if not entry:
        raise ValidationError('Journal entry not found.')
    if entry.status != 'DRAFT':
        raise ValidationError(f'Cannot post entry with status {entry.status}.')

    lines = list(entry.lines.all())
    if len(lines) < 2:
        raise ValidationError('Entry must have at least 2 lines.')

    total_debit = sum(l.amount for l in lines if l.side == 'DEBIT')
    total_credit = sum(l.amount for l in lines if l.side == 'CREDIT')
    if round(total_debit, 2) != round(total_credit, 2):
        raise ValidationError(f'Debits ({total_debit:.2f}) ≠ Credits ({total_credit:.2f}).')

    for line in lines:
        acct = line.account.single()
        if not acct or not acct.is_active:
            raise ValidationError(f'Line references an inactive or missing account.')

    from datetime import datetime
    entry.status = 'POSTED'
    entry.approved_by = approver_username
    entry.approved_at = datetime.utcnow()
    entry.save()
    return entry


def void_entry(entry_id: str, company_id: str, voider_username: str) -> JournalEntry:
    entry = JournalEntry.nodes.get_or_none(entry_id=entry_id, company_id=company_id)
    if not entry:
        raise ValidationError('Journal entry not found.')
    if entry.status != 'POSTED':
        raise ValidationError(f'Only POSTED entries can be voided. Current status: {entry.status}.')

    from datetime import datetime
    entry.status = 'VOID'
    entry.voided_by = voider_username
    entry.voided_at = datetime.utcnow()
    entry.save()
    return entry
