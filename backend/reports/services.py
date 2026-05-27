from neomodel import db

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


def compute_trial_balance(date_from: str, date_to: str) -> list:
    query = """
        MATCH (a:Account {is_active: true})
        OPTIONAL MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
        WHERE e.status = 'POSTED' AND e.date >= $date_from AND e.date <= $date_to
        RETURN
            a.account_id AS account_id,
            a.code AS code,
            a.name AS name,
            a.account_type AS account_type,
            a.normal_balance AS normal_balance,
            coalesce(sum(CASE WHEN l.side = 'DEBIT' THEN l.amount ELSE 0 END), 0) AS debits,
            coalesce(sum(CASE WHEN l.side = 'CREDIT' THEN l.amount ELSE 0 END), 0) AS credits
        ORDER BY a.code
    """
    results, _ = db.cypher_query(query, {'date_from': date_from, 'date_to': date_to})
    rows = []
    for r in results:
        account_id, code, name, acct_type, normal_bal, debits, credits = r
        debits = float(debits or 0)
        credits = float(credits or 0)
        rows.append({
            'account_id': account_id,
            'code': code,
            'name': name,
            'account_type': acct_type,
            'normal_balance': normal_bal,
            'total_debits': round(debits, 2),
            'total_credits': round(credits, 2),
            'balance': _account_balance(normal_bal, debits, credits),
        })
    return rows


def compute_income_statement(date_from: str, date_to: str) -> dict:
    all_types = REVENUE_TYPES + COS_TYPES + EXPENSE_TYPES
    query = """
        MATCH (a:Account {is_active: true})
        WHERE a.account_type IN $types
        OPTIONAL MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
        WHERE e.status = 'POSTED' AND e.date >= $date_from AND e.date <= $date_to
        RETURN
            a.account_id, a.code, a.name, a.account_type, a.normal_balance,
            coalesce(sum(CASE WHEN l.side = 'DEBIT' THEN l.amount ELSE 0 END), 0) AS debits,
            coalesce(sum(CASE WHEN l.side = 'CREDIT' THEN l.amount ELSE 0 END), 0) AS credits
        ORDER BY a.code
    """
    results, _ = db.cypher_query(query, {
        'types': all_types, 'date_from': date_from, 'date_to': date_to
    })
    revenue, cos, expenses = [], [], []
    for r in results:
        account_id, code, name, acct_type, normal_bal, debits, credits = r
        debits = float(debits or 0)
        credits = float(credits or 0)
        row = {
            'account_id': account_id, 'code': code, 'name': name,
            'account_type': acct_type,
            'balance': _account_balance(normal_bal, debits, credits),
        }
        if acct_type in REVENUE_TYPES:
            revenue.append(row)
        elif acct_type in COS_TYPES:
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


def compute_balance_sheet(as_of_date: str) -> dict:
    all_types = ASSET_TYPES + LIABILITY_TYPES + EQUITY_TYPES
    query = """
        MATCH (a:Account {is_active: true})
        WHERE a.account_type IN $types
        OPTIONAL MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
        WHERE e.status = 'POSTED' AND e.date <= $as_of_date
        RETURN
            a.account_id, a.code, a.name, a.account_type, a.normal_balance,
            coalesce(sum(CASE WHEN l.side = 'DEBIT' THEN l.amount ELSE 0 END), 0) AS debits,
            coalesce(sum(CASE WHEN l.side = 'CREDIT' THEN l.amount ELSE 0 END), 0) AS credits
        ORDER BY a.code
    """
    results, _ = db.cypher_query(query, {'types': all_types, 'as_of_date': as_of_date})
    assets, liabilities, equity = [], [], []
    for r in results:
        account_id, code, name, acct_type, normal_bal, debits, credits = r
        debits = float(debits or 0)
        credits = float(credits or 0)
        row = {
            'account_id': account_id, 'code': code, 'name': name,
            'account_type': acct_type,
            'balance': _account_balance(normal_bal, debits, credits),
        }
        if acct_type in ASSET_TYPES:
            assets.append(row)
        elif acct_type in LIABILITY_TYPES:
            liabilities.append(row)
        else:
            equity.append(row)

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


def compute_gl_detail(account_id: str, date_from: str, date_to: str) -> dict:
    account_query = "MATCH (a:Account {account_id: $account_id}) RETURN a.code, a.name, a.normal_balance"
    acct_result, _ = db.cypher_query(account_query, {'account_id': account_id})
    if not acct_result:
        return None
    code, name, normal_balance = acct_result[0]

    lines_query = """
        MATCH (a:Account {account_id: $account_id})
        MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
        WHERE e.status = 'POSTED' AND e.date >= $date_from AND e.date <= $date_to
        RETURN l.line_id, e.entry_id, e.reference, e.date, e.description,
               l.side, l.amount, l.description, e.entry_type
        ORDER BY e.date ASC, e.reference ASC
    """
    results, _ = db.cypher_query(lines_query, {
        'account_id': account_id, 'date_from': date_from, 'date_to': date_to
    })

    running_balance = 0.0
    lines = []
    for r in results:
        line_id, entry_id, reference, date, entry_desc, side, amount, line_desc, entry_type = r
        amount = float(amount or 0)
        if normal_balance == 'DEBIT':
            running_balance += amount if side == 'DEBIT' else -amount
        else:
            running_balance += amount if side == 'CREDIT' else -amount
        lines.append({
            'line_id': line_id,
            'entry_id': entry_id,
            'reference': reference,
            'date': str(date),
            'entry_description': entry_desc,
            'side': side,
            'amount': round(amount, 2),
            'line_description': line_desc,
            'entry_type': entry_type,
            'running_balance': round(running_balance, 2),
        })

    return {
        'account_id': account_id,
        'account_code': code,
        'account_name': name,
        'date_from': date_from,
        'date_to': date_to,
        'lines': lines,
        'closing_balance': round(running_balance, 2),
    }
