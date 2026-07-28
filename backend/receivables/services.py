from datetime import datetime, date as _date
from rest_framework.exceptions import ValidationError
from .models import SalesInvoice, ARReceipt, Customer


def _to_date(val):
    if isinstance(val, _date):
        return val
    return _date.fromisoformat(str(val))


def post_invoice(invoice_id: str, company_id: str, approver: str) -> SalesInvoice:
    invoice = SalesInvoice.nodes.get_or_none(invoice_id=invoice_id, company_id=company_id)
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status != 'DRAFT':
        raise ValidationError(f'Cannot post invoice with status {invoice.status}.')

    lines = list(invoice.lines.all())
    if not lines:
        raise ValidationError('Invoice has no lines.')

    total = round(sum(l.amount for l in lines), 2)
    ar_acct = invoice.ar_account.single()
    if not ar_acct:
        raise ValidationError('AR control account not set on invoice.')

    from journals.models import JournalEntry, JournalLine
    entry = JournalEntry(
        company_id=company_id,
        reference=f'AR-{invoice.invoice_number}',
        date=_to_date(invoice.date),
        description=f'Sales Invoice {invoice.invoice_number}',
        status='POSTED',
        entry_type='AR_RECEIPT',
        total_debit=total,
        total_credit=total,
        created_by=approver,
        approved_by=approver,
        approved_at=datetime.utcnow(),
    )
    entry.save()

    debit_line = JournalLine(company_id=company_id, side='DEBIT', amount=total, description=f'AR — {invoice.invoice_number}')
    debit_line.save()
    entry.lines.connect(debit_line)
    debit_line.account.connect(ar_acct)

    for line in lines:
        rev_acct = line.revenue_account.single()
        if not rev_acct:
            raise ValidationError(f'Line {line.line_id} has no revenue account.')
        jl = JournalLine(company_id=company_id, side='CREDIT', amount=line.amount, description=line.description)
        jl.save()
        entry.lines.connect(jl)
        jl.account.connect(rev_acct)

    invoice.journal_entry.connect(entry)
    invoice.status = 'POSTED'
    invoice.total_amount = total
    invoice.save()
    return invoice


def void_invoice(invoice_id: str, company_id: str, voider: str) -> SalesInvoice:
    invoice = SalesInvoice.nodes.get_or_none(invoice_id=invoice_id, company_id=company_id)
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status not in ('DRAFT', 'POSTED'):
        raise ValidationError(f'Cannot void invoice with status {invoice.status}.')
    if invoice.status == 'POSTED':
        je = invoice.journal_entry.single()
        if je:
            je.status = 'VOID'
            je.voided_by = voider
            je.voided_at = datetime.utcnow()
            je.save()
    invoice.status = 'VOID'
    invoice.save()
    return invoice


def record_receipt(invoice_id: str, company_id: str, receipt_date, amount: float,
                   reference: str, bank_account_id: str, username: str) -> ARReceipt:
    invoice = SalesInvoice.nodes.get_or_none(invoice_id=invoice_id, company_id=company_id)
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status != 'POSTED':
        raise ValidationError('Can only receive against POSTED invoices.')

    remaining = round(invoice.total_amount - invoice.amount_received, 2)
    if amount > remaining + 0.01:
        raise ValidationError(f'Receipt amount {amount:.2f} exceeds remaining balance {remaining:.2f}.')

    from banks.models import BankAccount
    bank = BankAccount.nodes.get_or_none(bank_account_id=bank_account_id, company_id=company_id)
    if not bank:
        raise ValidationError('Bank account not found.')
    bank_gl = bank.gl_account.single()
    if not bank_gl:
        raise ValidationError('Bank account has no linked GL account.')

    ar_acct = invoice.ar_account.single()
    amount = round(amount, 2)

    from journals.models import JournalEntry, JournalLine
    from banks.services import (
        generate_bank_transaction_reference,
        generate_invoice_settlement_reference,
    )
    entry = JournalEntry(
        company_id=company_id,
        reference=generate_invoice_settlement_reference('ARRec', invoice.invoice_number, company_id),
        date=_to_date(receipt_date),
        description=f'Receipt for {invoice.invoice_number}',
        status='POSTED',
        entry_type='AR_RECEIPT',
        total_debit=amount,
        total_credit=amount,
        created_by=username,
        approved_by=username,
        approved_at=datetime.utcnow(),
    )
    entry.save()

    dr = JournalLine(company_id=company_id, side='DEBIT', amount=amount, description='Bank receipt')
    dr.save()
    entry.lines.connect(dr)
    dr.account.connect(bank_gl)

    cr = JournalLine(company_id=company_id, side='CREDIT', amount=amount, description='AR receipt')
    cr.save()
    entry.lines.connect(cr)
    cr.account.connect(ar_acct)

    receipt = ARReceipt(
        company_id=company_id,
        receipt_date=_to_date(receipt_date),
        amount=amount,
        reference=reference,
        created_by=username,
    )
    receipt.save()
    receipt.invoice.connect(invoice)
    receipt.bank_account.connect(bank)
    receipt.journal_entry.connect(entry)

    from banks.models import BankTransaction
    bank_txn = BankTransaction(
        company_id=company_id,
        reference=generate_bank_transaction_reference(company_id),
        transaction_type='RECEIPT',
        date=_to_date(receipt_date),
        amount=amount,
        description=f'Receipt for {invoice.invoice_number}',
        created_by=username,
    )
    bank_txn.save()
    bank_txn.source_bank.connect(bank)
    bank_txn.journal_entry.connect(entry)
    customer = invoice.customer.single()
    if customer:
        bank_txn.customer.connect(customer)

    invoice.amount_received = round(invoice.amount_received + amount, 2)
    if invoice.amount_received >= invoice.total_amount - 0.01:
        invoice.status = 'PAID'
    invoice.save()
    return receipt


def get_customer_statement(customer_id: str, company_id: str) -> dict | None:
    customer = Customer.nodes.get_or_none(customer_id=customer_id, company_id=company_id)
    if not customer:
        return None

    invoices = [i for i in customer.invoices.all() if i.status in ('POSTED', 'PAID')]

    events = []
    for invoice in invoices:
        events.append({
            'date': invoice.date,
            'type': 'INVOICE',
            'reference': invoice.invoice_number,
            'description': invoice.description or f'Invoice {invoice.invoice_number}',
            'debit': round(invoice.total_amount, 2),
            'credit': 0.0,
        })
        for receipt in invoice.receipts.all():
            events.append({
                'date': receipt.receipt_date,
                'type': 'RECEIPT',
                'reference': receipt.reference or '',
                'description': f'Receipt for {invoice.invoice_number}',
                'debit': 0.0,
                'credit': round(receipt.amount, 2),
            })

    events.sort(key=lambda e: (str(e['date']), 0 if e['type'] == 'INVOICE' else 1))

    running_balance = 0.0
    lines = []
    for e in events:
        running_balance += e['debit'] - e['credit']
        lines.append({
            'date': str(e['date']),
            'type': e['type'],
            'reference': e['reference'],
            'description': e['description'],
            'debit': e['debit'],
            'credit': e['credit'],
            'running_balance': round(running_balance, 2),
        })

    return {
        'entity_id': customer.customer_id,
        'entity_name': customer.name,
        'lines': lines,
        'closing_balance': round(running_balance, 2),
    }
