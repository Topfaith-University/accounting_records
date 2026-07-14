from neomodel import db


def compute_account_balance(account_id: str, as_of_date=None) -> float:
    params = {'account_id': account_id}
    date_clause = ''
    if as_of_date:
        date_clause = 'AND e.date <= $as_of_date'
        params['as_of_date'] = str(as_of_date)

    query = f"""
        MATCH (a:Account {{account_id: $account_id}})
        OPTIONAL MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
        WHERE e.status = 'POSTED' {date_clause}
        RETURN
            a.normal_balance AS normal_balance,
            coalesce(sum(CASE WHEN l.side = 'DEBIT' THEN l.amount ELSE 0 END), 0) AS total_debits,
            coalesce(sum(CASE WHEN l.side = 'CREDIT' THEN l.amount ELSE 0 END), 0) AS total_credits
    """
    results, _ = db.cypher_query(query, params)
    if not results:
        return 0.0

    normal_balance, total_debits, total_credits = results[0]
    total_debits = total_debits or 0.0
    total_credits = total_credits or 0.0

    if normal_balance == 'DEBIT':
        return round(total_debits - total_credits, 2)
    else:
        return round(total_credits - total_debits, 2)


def get_or_create_opening_balance_equity_account():
    from .models import Account
    acct = Account.nodes.get_or_none(code='3900')
    if acct:
        return acct
    acct = Account(
        code='3900',
        name='Opening Balance Equity',
        account_type="Owner's Equity",
        normal_balance='CREDIT',
        description='System account — contra side of opening balance postings.',
        is_system=True,
    )
    acct.save()
    return acct


def post_opening_balance_entry(account, opening_balance, as_of_date, username):
    """Posts a journal entry seeding `account`'s opening balance against
    Opening Balance Equity. Idempotent — skips if already posted for this account."""
    from journals.models import JournalEntry, JournalLine
    from datetime import datetime

    if not opening_balance:
        return None

    reference = f'OB-{account.account_id}'
    if JournalEntry.nodes.get_or_none(reference=reference):
        return None  # already posted, never repost

    equity_acct = get_or_create_opening_balance_equity_account()

    entry = JournalEntry(
        reference=reference,
        date=as_of_date,
        description=f'Opening balance — {account.name}',
        status='POSTED',
        entry_type='MANUAL',
        total_debit=abs(opening_balance),
        total_credit=abs(opening_balance),
        created_by=username,
        approved_by=username,
        approved_at=datetime.utcnow(),
    )
    entry.save()

    # Positive opening_balance means the account should show its normal_balance
    # side increased; equity is always the contra side.
    account_side = 'DEBIT' if account.normal_balance == 'DEBIT' else 'CREDIT'
    equity_side = 'CREDIT' if account_side == 'DEBIT' else 'DEBIT'
    if opening_balance < 0:
        account_side, equity_side = equity_side, account_side

    acct_line = JournalLine(side=account_side, amount=abs(opening_balance), description='Opening balance')
    acct_line.save()
    entry.lines.connect(acct_line)
    acct_line.account.connect(account)

    equity_line = JournalLine(side=equity_side, amount=abs(opening_balance), description=f'Opening balance — {account.name}')
    equity_line.save()
    entry.lines.connect(equity_line)
    equity_line.account.connect(equity_acct)

    return entry
