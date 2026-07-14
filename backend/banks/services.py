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


# Note: the MERGE counter increments atomically but is not rolled back if the
# subsequent entry.save() fails. Reference gaps are possible under hard failures.
def generate_bank_transaction_reference() -> str:
    year = _date.today().year
    prefix = f'BT-{year}-'
    results, _ = db.cypher_query(
        """
        MERGE (c:BankTxnCounter {year: $year})
        ON CREATE SET c.seq = 1
        ON MATCH SET c.seq = c.seq + 1
        RETURN c.seq
        """,
        {'year': year}
    )
    seq = int(results[0][0])
    return f'{prefix}{seq:04d}'


def generate_invoice_settlement_reference(prefix: str, invoice_number: str) -> str:
    results, _ = db.cypher_query(
        """
        MERGE (c:InvoiceSettlementCounter {prefix: $prefix, invoice_number: $invoice_number})
        ON CREATE SET c.seq = 1
        ON MATCH SET c.seq = c.seq + 1
        RETURN c.seq
        """,
        {'prefix': prefix, 'invoice_number': invoice_number},
    )
    return f'{prefix}-{invoice_number}-{int(results[0][0]):04d}'


def create_bank_transaction(
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

    source_bank = BankAccount.nodes.get_or_none(bank_account_id=source_bank_id)
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
        dest_bank = BankAccount.nodes.get_or_none(bank_account_id=destination_bank_id)
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
            contra_acct = Account.nodes.get_or_none(account_id=split['account_id'])
            if not contra_acct:
                raise ValidationError(f"Account {split['account_id']} not found.")
            resolved_splits.append({
                'acct': contra_acct,
                'amount': split_amount,
                'description': split.get('description', ''),
            })
        total_amount = sum(s['amount'] for s in resolved_splits)

    reference = reference or generate_bank_transaction_reference()
    now = datetime.utcnow()

    entry = JournalEntry(
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
        # Fix 1: Use pre-resolved splits — no further DB lookups, no orphan risk
        for split in resolved_splits:
            split_line = JournalLine(
                side=contra_side,
                amount=split['amount'],
                description=split['description'],
            )
            split_line.save()
            split_line.account.connect(split['acct'])
            entry.lines.connect(split_line)

    txn = BankTransaction(
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
        vendor_node = Vendor.nodes.get_or_none(vendor_id=vendor_id)
        if vendor_node:
            txn.vendor.connect(vendor_node)

    if customer_id:
        from receivables.models import Customer
        customer_node = Customer.nodes.get_or_none(customer_id=customer_id)
        if customer_node:
            txn.customer.connect(customer_node)

    return txn
