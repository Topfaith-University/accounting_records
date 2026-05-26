from neomodel import db
from .models import BankAccount, BankTransaction
from journals.models import JournalEntry, JournalLine
from accounts.models import Account


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


def generate_bank_transaction_reference() -> str:
    from datetime import date
    year = date.today().year
    results, _ = db.cypher_query(
        "MATCH (t:BankTransaction) WHERE t.reference STARTS WITH $prefix RETURN count(t)",
        {'prefix': f'BT-{year}-'}
    )
    count = int(results[0][0]) if results else 0
    return f'BT-{year}-{count + 1:04d}'


def create_bank_transaction(
    transaction_type: str,
    date,
    description: str,
    source_bank_id: str,
    destination_bank_id,
    splits: list,
    amount,
    created_by: str,
):
    from rest_framework.exceptions import ValidationError
    from datetime import datetime

    source_bank = BankAccount.nodes.get_or_none(bank_account_id=source_bank_id)
    if not source_bank:
        raise ValidationError('Source bank account not found.')
    source_gl = source_bank.gl_account.single()
    if not source_gl:
        raise ValidationError('Source bank account has no linked GL account.')

    if transaction_type == 'TRANSFER':
        if not destination_bank_id:
            raise ValidationError('destination_bank_id is required for TRANSFER.')
        if destination_bank_id == source_bank_id:
            raise ValidationError('Source and destination bank accounts must differ.')
        dest_bank = BankAccount.nodes.get_or_none(bank_account_id=destination_bank_id)
        if not dest_bank:
            raise ValidationError('Destination bank account not found.')
        dest_gl = dest_bank.gl_account.single()
        if not dest_gl:
            raise ValidationError('Destination bank account has no linked GL account.')
        if not amount or float(amount) <= 0:
            raise ValidationError('Amount must be positive for TRANSFER.')
        total_amount = float(amount)
    else:
        if not splits:
            raise ValidationError('At least one split is required.')
        for split in splits:
            if float(split['amount']) <= 0:
                raise ValidationError('Each split amount must be positive.')
        total_amount = sum(float(s['amount']) for s in splits)

    reference = generate_bank_transaction_reference()
    now = datetime.utcnow()

    entry = JournalEntry(
        reference=reference,
        date=date,
        description=description,
        status='POSTED',
        entry_type='BANK_TRANSACTION',
        total_debit=total_amount,
        total_credit=total_amount,
        created_by=created_by,
        approved_by=created_by,
        approved_at=now,
    )
    entry.save()

    if transaction_type == 'TRANSFER':
        credit_line = JournalLine(side='CREDIT', amount=total_amount, description=description)
        credit_line.save()
        credit_line.account.connect(source_gl)
        entry.lines.connect(credit_line)

        debit_line = JournalLine(side='DEBIT', amount=total_amount, description=description)
        debit_line.save()
        debit_line.account.connect(dest_gl)
        entry.lines.connect(debit_line)
    else:
        bank_side = 'DEBIT' if transaction_type == 'RECEIPT' else 'CREDIT'
        bank_line = JournalLine(side=bank_side, amount=total_amount, description=description)
        bank_line.save()
        bank_line.account.connect(source_gl)
        entry.lines.connect(bank_line)

        contra_side = 'CREDIT' if transaction_type == 'RECEIPT' else 'DEBIT'
        for split in splits:
            contra_acct = Account.nodes.get_or_none(account_id=split['account_id'])
            if not contra_acct:
                raise ValidationError(f"Account {split['account_id']} not found.")
            split_line = JournalLine(
                side=contra_side,
                amount=float(split['amount']),
                description=split.get('description', ''),
            )
            split_line.save()
            split_line.account.connect(contra_acct)
            entry.lines.connect(split_line)

    txn = BankTransaction(
        reference=reference,
        transaction_type=transaction_type,
        date=date,
        amount=total_amount,
        description=description,
        created_by=created_by,
    )
    txn.save()
    txn.source_bank.connect(source_bank)
    if transaction_type == 'TRANSFER':
        txn.destination_bank.connect(dest_bank)
    txn.journal_entry.connect(entry)

    return txn
