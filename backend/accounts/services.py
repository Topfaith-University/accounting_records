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
