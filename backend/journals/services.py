from neomodel import db
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


def get_export_lines(company_id: str, date_from: str = None, date_to: str = None) -> list:
    """One row per JournalLine (not per entry) — each entry can post to several
    accounts (e.g. an AP invoice debits several expense accounts), so a
    per-entry summary can't show which account each amount actually hit.
    """
    # JournalEntry.date is stored as an ISO 'YYYY-MM-DD' string, not a native
    # Neo4j Date — compare the string directly rather than wrapping in date(),
    # which silently matches nothing (see banks/views.py for the same gotcha).
    conditions = []
    params = {'company_id': company_id}
    if date_from:
        conditions.append('e.date >= $date_from')
        params['date_from'] = date_from
    if date_to:
        conditions.append('e.date <= $date_to')
        params['date_to'] = date_to
    where_clause = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    query = f"""
        MATCH (e:JournalEntry {{company_id: $company_id}})-[:HAS_LINE]->(l:JournalLine)
        {where_clause}
        OPTIONAL MATCH (l)-[:AFFECTS_ACCOUNT]->(a:Account)
        RETURN e.reference, e.date, e.description, e.status,
               l.side, l.amount, l.description, a.name
        ORDER BY e.date DESC, e.reference DESC, l.side ASC
    """
    results, _ = db.cypher_query(query, params)
    rows = []
    for reference, date, entry_desc, entry_status, side, amount, line_desc, account_name in results:
        amount = float(amount or 0)
        rows.append({
            'reference': reference,
            'date': str(date),
            'account': account_name or '',
            'description': line_desc or entry_desc,
            'debit': amount if side == 'DEBIT' else 0.0,
            'credit': amount if side == 'CREDIT' else 0.0,
            'status': entry_status,
        })
    return rows


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
