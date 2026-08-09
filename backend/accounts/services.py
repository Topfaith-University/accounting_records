from datetime import datetime
from django.utils import timezone

from django.db import transaction
from django.db.models import Case, F, Q, Sum, Value, When, FloatField
from django.db.models.functions import Coalesce


def compute_account_balance(account_id: str, as_of_date=None) -> float:
    from .models import Account

    line_filter = Q(journal_lines__entry__status='POSTED')
    if as_of_date:
        line_filter &= Q(journal_lines__entry__date__lte=as_of_date)

    row = Account.objects.filter(pk=account_id).annotate(
        total_debits=Coalesce(Sum(Case(
            When(line_filter & Q(journal_lines__side='DEBIT'), then=F('journal_lines__amount')),
            default=Value(0.0), output_field=FloatField(),
        )), 0.0),
        total_credits=Coalesce(Sum(Case(
            When(line_filter & Q(journal_lines__side='CREDIT'), then=F('journal_lines__amount')),
            default=Value(0.0), output_field=FloatField(),
        )), 0.0),
    ).values('normal_balance', 'total_debits', 'total_credits').first()

    if not row:
        return 0.0

    total_debits = row['total_debits'] or 0.0
    total_credits = row['total_credits'] or 0.0
    if row['normal_balance'] == 'DEBIT':
        return round(total_debits - total_credits, 2)
    return round(total_credits - total_debits, 2)


def get_or_create_opening_balance_equity_account(company_id):
    from .models import Account

    acct = Account.objects.filter(code='3900', company_id=company_id).first()
    if acct:
        return acct
    return Account.objects.create(
        company_id=company_id,
        code='3900',
        name='Opening Balance Equity',
        account_type="Owner's Equity",
        normal_balance='CREDIT',
        description='System account — contra side of opening balance postings.',
        is_system=True,
    )


@transaction.atomic
def post_opening_balance_entry(account, opening_balance, as_of_date, user, reference_key=None):
    """Posts a journal entry seeding `account`'s opening balance against
    Opening Balance Equity. Idempotent — skips if already posted for this
    reference_key (defaults to the GL account's own id).

    `reference_key` matters when the caller isn't the GL account itself — e.g.
    a BankAccount posting its opening balance into a *linked* GL account. Two
    different bank accounts can legitimately share one GL account, each with
    its own opening balance, so callers in that position must pass their own
    stable id (e.g. the bank account's id) combined with the GL account's id
    — the combination, not the bank account id alone, because re-linking the
    *same* bank account to a *different* GL account must still re-trigger a
    fresh posting into that new account (existing, intended behavior).
    """
    from journals.models import JournalEntry, JournalLine

    if not opening_balance:
        return None

    company_id = account.company_id
    key = f'{reference_key}-{account.account_id}' if reference_key else account.account_id
    reference = f'OB-{key}'
    if JournalEntry.objects.filter(reference=reference, company_id=company_id).exists():
        return None  # already posted, never repost

    equity_acct = get_or_create_opening_balance_equity_account(company_id)

    entry = JournalEntry.objects.create(
        company_id=company_id,
        reference=reference,
        date=as_of_date,
        description=f'Opening balance — {account.name}',
        status='POSTED',
        entry_type='MANUAL',
        total_debit=abs(opening_balance),
        total_credit=abs(opening_balance),
        created_by=user,
        approved_by=user,
        approved_at=timezone.now(),
    )

    # Positive opening_balance means the account should show its normal_balance
    # side increased; equity is always the contra side.
    account_side = 'DEBIT' if account.normal_balance == 'DEBIT' else 'CREDIT'
    equity_side = 'CREDIT' if account_side == 'DEBIT' else 'DEBIT'
    if opening_balance < 0:
        account_side, equity_side = equity_side, account_side

    JournalLine.objects.create(
        company_id=company_id, entry=entry, account=account,
        side=account_side, amount=abs(opening_balance), description='Opening balance',
    )
    JournalLine.objects.create(
        company_id=company_id, entry=entry, account=equity_acct,
        side=equity_side, amount=abs(opening_balance),
        description=f'Opening balance — {account.name}',
    )

    return entry
