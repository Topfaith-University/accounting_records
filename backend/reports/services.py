from datetime import date, timedelta

from django.db.models import Case, F, Sum, Value, When, FloatField
from django.db.models.functions import Coalesce

from accounts.models import Account
from journals.models import JournalLine

REVENUE_TYPES = ['Sales', 'Other Incomes']
COS_TYPES = ['Cost of Sales']
EXPENSE_TYPES = ['Expenses', 'Income Tax']
ASSET_TYPES = ['Non-Current Assets', 'Current Assets']
LIABILITY_TYPES = ['Current Liabilities', 'Non-Current Liabilities']
EQUITY_TYPES = ["Owner's Equity"]


def _account_balance(normal_balance, debits, credits):
    if normal_balance == 'DEBIT':
        return round(debits - credits, 2)
    return round(credits - debits, 2)


def _balances_by_account(company_id: str, account_types=None, date_from=None, date_to=None, as_of_date=None):
    """Every active account with total debits/credits from its POSTED
    JournalLines in range, via a single Case/When-inside-Sum annotate (NOT
    two separately-filtered Sum() annotations, which can double the join and
    inflate results — this is the one ORM idiom in the whole migration worth
    getting precisely right, mirroring the original Cypher's single
    OPTIONAL MATCH row set with CASE WHEN conditional aggregation).
    """
    qs = Account.objects.filter(is_active=True, company_id=company_id)
    if account_types:
        qs = qs.filter(account_type__in=account_types)

    line_filter = {'journal_lines__entry__status': 'POSTED'}
    if date_from:
        line_filter['journal_lines__entry__date__gte'] = date_from
    if date_to:
        line_filter['journal_lines__entry__date__lte'] = date_to
    if as_of_date:
        line_filter['journal_lines__entry__date__lte'] = as_of_date

    from django.db.models import Q
    match = Q(**line_filter)

    qs = qs.annotate(
        total_debits=Coalesce(Sum(Case(
            When(match & Q(journal_lines__side='DEBIT'), then=F('journal_lines__amount')),
            default=Value(0.0), output_field=FloatField(),
        )), 0.0),
        total_credits=Coalesce(Sum(Case(
            When(match & Q(journal_lines__side='CREDIT'), then=F('journal_lines__amount')),
            default=Value(0.0), output_field=FloatField(),
        )), 0.0),
    ).order_by('code')
    return qs


def compute_trial_balance(company_id: str, date_from: str, date_to: str) -> list:
    """Balance-sheet accounts (Assets/Liabilities/Equity) carry forward prior
    periods: shown as of date_to, ignoring date_from entirely — matching
    standard trial balance convention (and SAGE's own report) where these
    accounts are running balances, not period movement. P&L accounts
    (Sales/Cost of Sales/Expenses/Income Tax/Other Incomes) still reset each
    period and use date_from/date_to as a movement window. No plug row is
    added to force the two sides to tie — same as SAGE, an unclosed current
    period's net profit is expected to leave the totals apart until a
    year-end closing entry is posted.
    """
    bs_types = ASSET_TYPES + LIABILITY_TYPES + EQUITY_TYPES
    pl_types = REVENUE_TYPES + COS_TYPES + EXPENSE_TYPES
    accounts = list(_balances_by_account(company_id, account_types=bs_types, as_of_date=date_to)) + \
        list(_balances_by_account(company_id, account_types=pl_types, date_from=date_from, date_to=date_to))
    accounts.sort(key=lambda a: a.code)

    rows = []
    for a in accounts:
        debits = float(a.total_debits or 0)
        credits = float(a.total_credits or 0)
        rows.append({
            'account_id': a.account_id,
            'code': a.code,
            'name': a.name,
            'account_type': a.account_type,
            'normal_balance': a.normal_balance,
            'total_debits': round(debits, 2),
            'total_credits': round(credits, 2),
            'balance': _account_balance(a.normal_balance, debits, credits),
        })

    # No year-end closing entries exist in this app, so — like
    # compute_balance_sheet's live P&L rollup — prior periods' net effect is
    # folded into the Retained Income account on demand rather than posted.
    # Only activity strictly before date_from counts as "prior"; the current
    # period's own movement stays on its own P&L accounts above.
    try:
        day_before_from = (date.fromisoformat(date_from) - timedelta(days=1)).isoformat()
    except ValueError:
        day_before_from = None
    if day_before_from:
        prior_pl = compute_income_statement(company_id, '0001-01-01', day_before_from)
        if prior_pl['net_surplus'] != 0:
            for row in rows:
                if row['account_type'] in EQUITY_TYPES and row['name'] == 'Retained Income':
                    surplus = prior_pl['net_surplus']
                    if surplus < 0:
                        row['total_debits'] = round(row['total_debits'] + abs(surplus), 2)
                    else:
                        row['total_credits'] = round(row['total_credits'] + surplus, 2)
                    row['balance'] = _account_balance(row['normal_balance'], row['total_debits'], row['total_credits'])
                    break

    return rows


def compute_income_statement(company_id: str, date_from: str, date_to: str) -> dict:
    all_types = REVENUE_TYPES + COS_TYPES + EXPENSE_TYPES
    accounts = _balances_by_account(company_id, account_types=all_types, date_from=date_from, date_to=date_to)

    revenue, cos, expenses = [], [], []
    for a in accounts:
        debits = float(a.total_debits or 0)
        credits = float(a.total_credits or 0)
        row = {
            'account_id': a.account_id, 'code': a.code, 'name': a.name,
            'account_type': a.account_type,
            'balance': _account_balance(a.normal_balance, debits, credits),
        }
        if a.account_type in REVENUE_TYPES:
            revenue.append(row)
        elif a.account_type in COS_TYPES:
            cos.append(row)
        else:
            expenses.append(row)

    total_revenue = sum(r['balance'] for r in revenue)
    total_cos = sum(r['balance'] for r in cos)
    total_expenses = sum(r['balance'] for r in expenses)
    gross_profit = round(total_revenue - total_cos, 2)
    net_surplus = round(gross_profit - total_expenses, 2)

    return {
        'date_from': date_from,
        'date_to': date_to,
        'revenue': revenue,
        'total_revenue': round(total_revenue, 2),
        'cost_of_sales': cos,
        'total_cos': round(total_cos, 2),
        'gross_profit': gross_profit,
        'expenses': expenses,
        'total_expenses': round(total_expenses, 2),
        'net_surplus': net_surplus,
    }


def compute_balance_sheet(company_id: str, as_of_date: str) -> dict:
    all_types = ASSET_TYPES + LIABILITY_TYPES + EQUITY_TYPES
    accounts = _balances_by_account(company_id, account_types=all_types, as_of_date=as_of_date)

    assets, liabilities, equity = [], [], []
    for a in accounts:
        debits = float(a.total_debits or 0)
        credits = float(a.total_credits or 0)
        row = {
            'account_id': a.account_id, 'code': a.code, 'name': a.name,
            'account_type': a.account_type,
            'balance': _account_balance(a.normal_balance, debits, credits),
        }
        if a.account_type in ASSET_TYPES:
            assets.append(row)
        elif a.account_type in LIABILITY_TYPES:
            liabilities.append(row)
        else:
            equity.append(row)

    # Cumulative Profit/Loss since inception, rolled into Equity (no closing-entry
    # mechanism exists yet, so this is computed live rather than posted).
    pl = compute_income_statement(company_id, '0001-01-01', as_of_date)
    if pl['net_surplus'] != 0:
        equity.append({
            'account_id': None,
            'code': '',
            'name': 'Profit/(Loss) — current & prior periods',
            'account_type': "Owner's Equity",
            'balance': pl['net_surplus'],
        })

    total_assets = round(sum(r['balance'] for r in assets), 2)
    total_liabilities = round(sum(r['balance'] for r in liabilities), 2)
    total_equity = round(sum(r['balance'] for r in equity), 2)

    return {
        'as_of_date': as_of_date,
        'assets': assets,
        'total_assets': total_assets,
        'liabilities': liabilities,
        'total_liabilities': total_liabilities,
        'equity': equity,
        'total_equity': total_equity,
        'is_balanced': abs(total_assets - (total_liabilities + total_equity)) < 0.01,
    }


def compute_gl_detail(company_id: str, account_id: str, date_from: str, date_to: str) -> dict:
    account = Account.objects.filter(account_id=account_id, company_id=company_id).first()
    if not account:
        return None

    lines = (
        JournalLine.objects
        .filter(
            account_id=account_id, entry__company_id=company_id, entry__status='POSTED',
            entry__date__gte=date_from, entry__date__lte=date_to,
        )
        .select_related('entry')
        .order_by('entry__date', 'entry__reference')
    )

    running_balance = 0.0
    result_lines = []
    for line in lines:
        amount = float(line.amount or 0)
        if account.normal_balance == 'DEBIT':
            running_balance += amount if line.side == 'DEBIT' else -amount
        else:
            running_balance += amount if line.side == 'CREDIT' else -amount
        result_lines.append({
            'line_id': line.line_id,
            'entry_id': line.entry.entry_id,
            'reference': line.entry.reference,
            'date': str(line.entry.date),
            'entry_description': line.entry.description,
            'side': line.side,
            'amount': round(amount, 2),
            'line_description': line.description,
            'entry_type': line.entry.entry_type,
            'running_balance': round(running_balance, 2),
        })

    return {
        'account_id': account_id,
        'account_code': account.code,
        'account_name': account.name,
        'date_from': date_from,
        'date_to': date_to,
        'lines': result_lines,
        'closing_balance': round(running_balance, 2),
    }
