from datetime import datetime, date as _date
from django.utils import timezone

from django.db import transaction
from django.db.models import Sum, Case, When, F, FloatField
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from .models import BankAccount, BankTransaction
from journals.models import JournalEntry, JournalLine, Counter
from accounts.models import Account


def _to_date(val):
    if isinstance(val, _date):
        return val
    return _date.fromisoformat(str(val))


def compute_bank_current_balance(bank_account_id: str, company_id: str) -> float:
    """Opening balance plus this bank's own BankTransaction movements only —
    deliberately independent of the GL account balance, which can be polluted
    by other bank accounts sharing the same GL account or by direct GL postings.
    """
    ba = BankAccount.objects.filter(bank_account_id=bank_account_id, company_id=company_id).first()
    if not ba:
        return 0.0

    source_movement = BankTransaction.objects.filter(
        source_bank_id=bank_account_id, company_id=company_id,
    ).aggregate(
        total=Coalesce(Sum(Case(
            When(transaction_type='RECEIPT', then=F('amount')),
            default=-F('amount'), output_field=FloatField(),
        )), 0.0),
    )['total'] or 0.0

    dest_movement = BankTransaction.objects.filter(
        destination_bank_id=bank_account_id, company_id=company_id, transaction_type='TRANSFER',
    ).aggregate(total=Coalesce(Sum('amount'), 0.0))['total'] or 0.0

    return round((ba.opening_balance or 0.0) + source_movement + dest_movement, 2)


def get_account_names_for_transactions(transaction_ids: list, company_id: str) -> dict:
    """Maps transaction_id -> '; '-joined name(s) of the GL account(s) each
    transaction posted against, excluding the source bank's own GL account —
    i.e. the expense/revenue account a PAYMENT/RECEIPT split hit, or the
    destination bank's GL account for a TRANSFER (bank GL accounts are named
    after their bank, so this reads as the counterparty bank).
    """
    if not transaction_ids:
        return {}
    rows = (
        JournalLine.objects
        .filter(
            entry__bank_transactions__transaction_id__in=transaction_ids,
            entry__bank_transactions__company_id=company_id,
        )
        .values_list(
            'entry__bank_transactions__transaction_id',
            'account__name',
            'account_id',
            'entry__bank_transactions__source_bank__gl_account_id',
        )
        .order_by('entry__bank_transactions__transaction_id')
    )
    names_by_txn = {}
    for txn_id, acct_name, acct_id, source_gl_id in rows:
        if source_gl_id is not None and acct_id == source_gl_id:
            continue
        names_by_txn.setdefault(txn_id, [])
        if acct_name not in names_by_txn[txn_id]:
            names_by_txn[txn_id].append(acct_name)
    return {txn_id: '; '.join(names) for txn_id, names in names_by_txn.items()}


def get_bank_gl_lines(bank_account_id: str, company_id: str, recon_id: str = None) -> list:
    ba = BankAccount.objects.filter(bank_account_id=bank_account_id, company_id=company_id).first()
    if not ba or not ba.gl_account_id:
        return []

    lines = (
        JournalLine.objects
        .filter(account_id=ba.gl_account_id, entry__company_id=company_id, entry__status='POSTED')
        .select_related('entry')
        .order_by('entry__date')
    )

    reconciled_ids = set()
    if recon_id:
        reconciled_ids = set(
            JournalLine.objects.filter(reconciliations__reconciliation_id=recon_id)
            .values_list('line_id', flat=True)
        )

    return [
        {
            'line_id': line.line_id,
            'entry_id': line.entry.entry_id,
            'reference': line.entry.reference,
            'date': str(line.entry.date),
            'entry_description': line.entry.description,
            'side': line.side,
            'amount': line.amount,
            'line_description': line.description,
            'is_reconciled': line.line_id in reconciled_ids,
        }
        for line in lines
    ]


def generate_bank_transaction_reference(company_id: str) -> str:
    year = _date.today().year
    seq = Counter.next(f'BT-{year}-{company_id}')
    return f'BT-{year}-{seq:04d}'


def generate_invoice_settlement_reference(prefix: str, invoice_number: str, company_id: str) -> str:
    seq = Counter.next(f'{prefix}-{invoice_number}-{company_id}')
    return f'{prefix}-{invoice_number}-{seq:04d}'


@transaction.atomic
def create_bank_transaction(
    company_id: str,
    transaction_type: str,
    txn_date,
    description: str,
    source_bank_id: str,
    destination_bank_id,
    splits: list,
    amount,
    created_by,
    vendor_id=None,
    customer_id=None,
    reference=None,
):
    VALID_TYPES = {'RECEIPT', 'PAYMENT', 'TRANSFER'}
    if transaction_type not in VALID_TYPES:
        raise ValidationError(f"transaction_type must be one of {sorted(VALID_TYPES)}.")

    source_bank = BankAccount.objects.filter(
        bank_account_id=source_bank_id, company_id=company_id,
    ).select_related('gl_account').first()
    if not source_bank:
        raise ValidationError('Source bank account not found.')
    source_gl = source_bank.gl_account
    if not source_gl:
        raise ValidationError(
            f'Bank account "{source_bank.name}" has no linked GL account. '
            'Edit the bank account and assign a GL account before posting transactions.'
        )

    dest_bank = None
    dest_gl = None
    resolved_splits = []

    if transaction_type == 'TRANSFER':
        if not destination_bank_id:
            raise ValidationError('destination_bank_id is required for TRANSFER.')
        if destination_bank_id == source_bank_id:
            raise ValidationError('Source and destination bank accounts must differ.')
        dest_bank = BankAccount.objects.filter(
            bank_account_id=destination_bank_id, company_id=company_id,
        ).select_related('gl_account').first()
        if not dest_bank:
            raise ValidationError('Destination bank account not found.')
        dest_gl = dest_bank.gl_account
        if not dest_gl:
            raise ValidationError(
                f'Bank account "{dest_bank.name}" has no linked GL account. '
                'Edit the bank account and assign a GL account before posting transactions.'
            )
        try:
            total_amount = float(amount)
        except (TypeError, ValueError):
            raise ValidationError('Amount must be a valid number for TRANSFER.')
        if total_amount <= 0:
            raise ValidationError('Amount must be positive for TRANSFER.')
    else:
        if not splits:
            raise ValidationError('At least one split is required.')
        for split in splits:
            try:
                split_amount = float(split['amount'])
            except (TypeError, ValueError):
                raise ValidationError('Split amount must be a valid number.')
            if split_amount <= 0:
                raise ValidationError('Each split amount must be positive.')
            contra_acct = Account.objects.filter(account_id=split['account_id'], company_id=company_id).first()
            if not contra_acct:
                raise ValidationError(f"Account {split['account_id']} not found.")
            resolved_splits.append({
                'acct': contra_acct,
                'amount': split_amount,
                'description': split.get('description', ''),
            })
        total_amount = sum(s['amount'] for s in resolved_splits)

    reference = reference or generate_bank_transaction_reference(company_id)
    now = timezone.now()

    entry = JournalEntry.objects.create(
        company_id=company_id,
        reference=reference,
        date=_to_date(txn_date),
        description=description,
        status='POSTED',
        entry_type='BANK_TRANSACTION',
        total_debit=total_amount,
        total_credit=total_amount,
        created_by=created_by,
        approved_by=created_by,
        approved_at=now,
    )

    if transaction_type == 'TRANSFER':
        JournalLine.objects.create(
            company_id=company_id, entry=entry, account=source_gl,
            side='CREDIT', amount=total_amount, description=description,
        )
        JournalLine.objects.create(
            company_id=company_id, entry=entry, account=dest_gl,
            side='DEBIT', amount=total_amount, description=description,
        )
    else:
        bank_side = 'DEBIT' if transaction_type == 'RECEIPT' else 'CREDIT'
        JournalLine.objects.create(
            company_id=company_id, entry=entry, account=source_gl,
            side=bank_side, amount=total_amount, description=description,
        )
        contra_side = 'CREDIT' if transaction_type == 'RECEIPT' else 'DEBIT'
        for split in resolved_splits:
            JournalLine.objects.create(
                company_id=company_id, entry=entry, account=split['acct'],
                side=contra_side, amount=split['amount'], description=split['description'],
            )

    txn = BankTransaction.objects.create(
        company_id=company_id,
        reference=reference,
        transaction_type=transaction_type,
        date=_to_date(txn_date),
        amount=total_amount,
        description=description,
        created_by=created_by,
        source_bank=source_bank,
        destination_bank=dest_bank if transaction_type == 'TRANSFER' else None,
        journal_entry=entry,
    )

    if vendor_id:
        from payables.models import Vendor
        vendor = Vendor.objects.filter(vendor_id=vendor_id, company_id=company_id).first()
        if vendor:
            txn.vendor = vendor
            txn.save(update_fields=['vendor'])

    if customer_id:
        from receivables.models import Customer
        customer = Customer.objects.filter(customer_id=customer_id, company_id=company_id).first()
        if customer:
            txn.customer = customer
            txn.save(update_fields=['customer'])

    return txn
