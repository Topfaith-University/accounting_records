from neomodel import db
from rest_framework.exceptions import ValidationError
from datetime import datetime, date as _date
from .models import BankAccount, BankTransaction
from journals.models import JournalEntry, JournalLine
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
    query = """
        MATCH (ba:BankAccount {bank_account_id: $bank_account_id, company_id: $company_id})
        OPTIONAL MATCH (t:BankTransaction {company_id: $company_id})-[:FROM_BANK]->(ba)
        WITH ba, coalesce(sum(
            CASE t.transaction_type WHEN 'RECEIPT' THEN t.amount ELSE -t.amount END
        ), 0) AS source_movement
        OPTIONAL MATCH (t2:BankTransaction {company_id: $company_id, transaction_type: 'TRANSFER'})-[:TO_BANK]->(ba)
        RETURN ba.opening_balance, source_movement, coalesce(sum(t2.amount), 0)
    """
    results, _ = db.cypher_query(query, {'bank_account_id': bank_account_id, 'company_id': company_id})
    if not results:
        return 0.0
    opening_balance, source_movement, dest_movement = results[0]
    return round((opening_balance or 0.0) + (source_movement or 0.0) + (dest_movement or 0.0), 2)


def get_account_names_for_transactions(transaction_ids: list, company_id: str) -> dict:
    """Maps transaction_id -> '; '-joined name(s) of the GL account(s) each
    transaction posted against, excluding the source bank's own GL account —
    i.e. the expense/revenue account a PAYMENT/RECEIPT split hit, or the
    destination bank's GL account for a TRANSFER (bank GL accounts are named
    after their bank, so this reads as the counterparty bank).
    """
    if not transaction_ids:
        return {}
    query = """
        MATCH (t:BankTransaction {company_id: $company_id})-[:GENERATES_ENTRY]->(e:JournalEntry)
              -[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a:Account)
        WHERE t.transaction_id IN $ids
        OPTIONAL MATCH (t)-[:FROM_BANK]->(:BankAccount)-[:MAPS_TO_ACCOUNT]->(source_gl:Account)
        WITH t, a, source_gl
        WHERE source_gl IS NULL OR a.account_id <> source_gl.account_id
        RETURN t.transaction_id, a.name
        ORDER BY t.transaction_id
    """
    results, _ = db.cypher_query(query, {'ids': transaction_ids, 'company_id': company_id})
    names_by_txn = {}
    for txn_id, name in results:
        names_by_txn.setdefault(txn_id, [])
        if name not in names_by_txn[txn_id]:
            names_by_txn[txn_id].append(name)
    return {txn_id: '; '.join(names) for txn_id, names in names_by_txn.items()}


def get_bank_gl_lines(bank_account_id: str, company_id: str, recon_id: str = None) -> list:
    params = {'bank_account_id': bank_account_id, 'company_id': company_id}

    if recon_id:
        params['recon_id'] = recon_id
        query = """
            MATCH (ba:BankAccount {bank_account_id: $bank_account_id, company_id: $company_id})
            MATCH (ba)-[:MAPS_TO_ACCOUNT]->(a:Account)
            MATCH (e:JournalEntry {company_id: $company_id})-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
            WHERE e.status = 'POSTED'
            OPTIONAL MATCH (r:BankReconciliation {reconciliation_id: $recon_id})-[:RECONCILES]->(l)
            RETURN l.line_id, e.entry_id, e.reference, e.date, e.description,
                   l.side, l.amount, l.description,
                   r.reconciliation_id IS NOT NULL AS is_reconciled
            ORDER BY e.date ASC
        """
    else:
        query = """
            MATCH (ba:BankAccount {bank_account_id: $bank_account_id, company_id: $company_id})
            MATCH (ba)-[:MAPS_TO_ACCOUNT]->(a:Account)
            MATCH (e:JournalEntry {company_id: $company_id})-[:HAS_LINE]->(l:JournalLine)-[:AFFECTS_ACCOUNT]->(a)
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


# Note: the MERGE counter increments atomically but is not rolled back if the
# subsequent entry.save() fails. Reference gaps are possible under hard failures.
def generate_bank_transaction_reference(company_id: str) -> str:
    year = _date.today().year
    prefix = f'BT-{year}-'
    results, _ = db.cypher_query(
        """
        MERGE (c:BankTxnCounter {year: $year, company_id: $company_id})
        ON CREATE SET c.seq = 1
        ON MATCH SET c.seq = c.seq + 1
        RETURN c.seq
        """,
        {'year': year, 'company_id': company_id}
    )
    seq = int(results[0][0])
    return f'{prefix}{seq:04d}'


def generate_invoice_settlement_reference(prefix: str, invoice_number: str, company_id: str) -> str:
    results, _ = db.cypher_query(
        """
        MERGE (c:InvoiceSettlementCounter {prefix: $prefix, invoice_number: $invoice_number, company_id: $company_id})
        ON CREATE SET c.seq = 1
        ON MATCH SET c.seq = c.seq + 1
        RETURN c.seq
        """,
        {'prefix': prefix, 'invoice_number': invoice_number, 'company_id': company_id},
    )
    return f'{prefix}-{invoice_number}-{int(results[0][0]):04d}'


def create_bank_transaction(
    company_id: str,
    transaction_type: str,
    txn_date,
    description: str,
    source_bank_id: str,
    destination_bank_id,
    splits: list,
    amount,
    created_by: str,
    vendor_id=None,
    customer_id=None,
    reference=None,
):
    # Fix 3: Validate transaction_type before any processing
    VALID_TYPES = {'RECEIPT', 'PAYMENT', 'TRANSFER'}
    if transaction_type not in VALID_TYPES:
        raise ValidationError(f"transaction_type must be one of {sorted(VALID_TYPES)}.")

    source_bank = BankAccount.nodes.get_or_none(bank_account_id=source_bank_id, company_id=company_id)
    if not source_bank:
        raise ValidationError('Source bank account not found.')
    try:
        source_gl = source_bank.gl_account.single()
    except Exception:
        source_gl = None
    if not source_gl:
        raise ValidationError(
            f'Bank account "{source_bank.name}" has no linked GL account. '
            'Edit the bank account and assign a GL account before posting transactions.'
        )

    # Fix 7: Guard dest_bank/dest_gl as possibly unbound
    dest_bank = None
    dest_gl = None

    if transaction_type == 'TRANSFER':
        if not destination_bank_id:
            raise ValidationError('destination_bank_id is required for TRANSFER.')
        if destination_bank_id == source_bank_id:
            raise ValidationError('Source and destination bank accounts must differ.')
        dest_bank = BankAccount.nodes.get_or_none(bank_account_id=destination_bank_id, company_id=company_id)
        if not dest_bank:
            raise ValidationError('Destination bank account not found.')
        try:
            dest_gl = dest_bank.gl_account.single()
        except Exception:
            dest_gl = None
        if not dest_gl:
            raise ValidationError(
                f'Bank account "{dest_bank.name}" has no linked GL account. '
                'Edit the bank account and assign a GL account before posting transactions.'
            )
        # Fix 4: Guard float() against non-numeric input for TRANSFER
        try:
            total_amount = float(amount)
        except (TypeError, ValueError):
            raise ValidationError('Amount must be a valid number for TRANSFER.')
        if total_amount <= 0:
            raise ValidationError('Amount must be positive for TRANSFER.')
    else:
        if not splits:
            raise ValidationError('At least one split is required.')
        # Fix 1: Resolve all split accounts BEFORE any .save() calls
        resolved_splits = []
        for split in splits:
            # Fix 4: Guard float() against non-numeric input for split amounts
            try:
                split_amount = float(split['amount'])
            except (TypeError, ValueError):
                raise ValidationError('Split amount must be a valid number.')
            if split_amount <= 0:
                raise ValidationError('Each split amount must be positive.')
            contra_acct = Account.nodes.get_or_none(account_id=split['account_id'], company_id=company_id)
            if not contra_acct:
                raise ValidationError(f"Account {split['account_id']} not found.")
            resolved_splits.append({
                'acct': contra_acct,
                'amount': split_amount,
                'description': split.get('description', ''),
            })
        total_amount = sum(s['amount'] for s in resolved_splits)

    reference = reference or generate_bank_transaction_reference(company_id)
    now = datetime.utcnow()

    entry = JournalEntry(
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
    entry.save()

    if transaction_type == 'TRANSFER':
        credit_line = JournalLine(company_id=company_id, side='CREDIT', amount=total_amount, description=description)
        credit_line.save()
        credit_line.account.connect(source_gl)
        entry.lines.connect(credit_line)

        debit_line = JournalLine(company_id=company_id, side='DEBIT', amount=total_amount, description=description)
        debit_line.save()
        debit_line.account.connect(dest_gl)
        entry.lines.connect(debit_line)
    else:
        bank_side = 'DEBIT' if transaction_type == 'RECEIPT' else 'CREDIT'
        bank_line = JournalLine(company_id=company_id, side=bank_side, amount=total_amount, description=description)
        bank_line.save()
        bank_line.account.connect(source_gl)
        entry.lines.connect(bank_line)

        contra_side = 'CREDIT' if transaction_type == 'RECEIPT' else 'DEBIT'
        # Fix 1: Use pre-resolved splits — no further DB lookups, no orphan risk
        for split in resolved_splits:
            split_line = JournalLine(
                company_id=company_id,
                side=contra_side,
                amount=split['amount'],
                description=split['description'],
            )
            split_line.save()
            split_line.account.connect(split['acct'])
            entry.lines.connect(split_line)

    txn = BankTransaction(
        company_id=company_id,
        reference=reference,
        transaction_type=transaction_type,
        date=_to_date(txn_date),
        amount=total_amount,
        description=description,
        created_by=created_by,
    )
    txn.save()
    txn.source_bank.connect(source_bank)
    if transaction_type == 'TRANSFER':
        txn.destination_bank.connect(dest_bank)
    txn.journal_entry.connect(entry)

    if vendor_id:
        from payables.models import Vendor
        vendor_node = Vendor.nodes.get_or_none(vendor_id=vendor_id, company_id=company_id)
        if vendor_node:
            txn.vendor.connect(vendor_node)

    if customer_id:
        from receivables.models import Customer
        customer_node = Customer.nodes.get_or_none(customer_id=customer_id, company_id=company_id)
        if customer_node:
            txn.customer.connect(customer_node)

    return txn
