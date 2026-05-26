from neomodel import db


def get_bank_gl_lines(bank_account_id: str, recon_id: str = None) -> list:
    params = {'bank_account_id': bank_account_id}

    if recon_id:
        params['recon_id'] = recon_id
        query = """
            MATCH (ba:BankAccount {bank_account_id: $bank_account_id})
            MATCH (ba)-[:MAPS_TO_ACCOUNT]->(a:Account)
            MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
            WHERE e.status = 'POSTED'
            OPTIONAL MATCH (r:BankReconciliation {reconciliation_id: $recon_id})-[:RECONCILES]->(l)
            RETURN l.line_id, e.entry_id, e.reference, e.date, e.description,
                   l.side, l.amount, l.description,
                   r.reconciliation_id IS NOT NULL AS is_reconciled
            ORDER BY e.date ASC
        """
    else:
        query = """
            MATCH (ba:BankAccount {bank_account_id: $bank_account_id})
            MATCH (ba)-[:MAPS_TO_ACCOUNT]->(a:Account)
            MATCH (e:JournalEntry)-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
            WHERE e.status = 'POSTED'
            RETURN l.line_id, e.entry_id, e.reference, e.date, e.description,
                   l.side, l.amount, l.description,
                   false AS is_reconciled
            ORDER BY e.date ASC
        """

    results, _ = db.cypher_query(query, params)
    return [
        {
            'line_id': r[0],
            'entry_id': r[1],
            'reference': r[2],
            'date': str(r[3]),
            'entry_description': r[4],
            'side': r[5],
            'amount': r[6],
            'line_description': r[7],
            'is_reconciled': bool(r[8]),
        }
        for r in results
    ]
