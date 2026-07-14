from datetime import datetime, date as _date
from rest_framework.exceptions import ValidationError
from .models import PurchaseInvoice, APPayment


def _to_date(val):
    if isinstance(val, _date):
        return val
    return _date.fromisoformat(str(val))


def post_invoice(invoice_id: str, approver: str) -> PurchaseInvoice:
    invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=invoice_id)
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status != 'DRAFT':
        raise ValidationError(f'Cannot post invoice with status {invoice.status}.')

    lines = list(invoice.lines.all())
    if not lines:
        raise ValidationError('Invoice has no lines.')

    total = round(sum(l.amount for l in lines), 2)
    ap_acct = invoice.ap_account.single()
    if not ap_acct:
        raise ValidationError('AP control account not set on invoice.')

    from journals.models import JournalEntry, JournalLine
    entry = JournalEntry(
        reference=f'AP-{invoice.invoice_number}',
        date=_to_date(invoice.date),
        description=f'Purchase Invoice {invoice.invoice_number}',
        status='POSTED',
        entry_type='AP_PAYMENT',
        total_debit=total,
        total_credit=total,
        created_by=approver,
        approved_by=approver,
        approved_at=datetime.utcnow(),
    )
    entry.save()

    for line in lines:
        expense_acct = line.expense_account.single()
        if not expense_acct:
            raise ValidationError(f'Line {line.line_id} has no expense account.')
        jl = JournalLine(side='DEBIT', amount=line.amount, description=line.description)
        jl.save()
        entry.lines.connect(jl)
        jl.account.connect(expense_acct)

    credit_line = JournalLine(side='CREDIT', amount=total, description=f'AP — {invoice.invoice_number}')
    credit_line.save()
    entry.lines.connect(credit_line)
    credit_line.account.connect(ap_acct)

    invoice.journal_entry.connect(entry)
    invoice.status = 'POSTED'
    invoice.total_amount = total
    invoice.save()
    return invoice


def void_invoice(invoice_id: str, voider: str) -> PurchaseInvoice:
    invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=invoice_id)
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


def record_payment(invoice_id: str, payment_date, amount: float,
                   reference: str, bank_account_id: str, username: str) -> APPayment:
    invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=invoice_id)
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status != 'POSTED':
        raise ValidationError('Can only pay POSTED invoices.')

    remaining = round(invoice.total_amount - invoice.amount_paid, 2)
    if amount > remaining + 0.01:
        raise ValidationError(f'Payment amount {amount:.2f} exceeds remaining balance {remaining:.2f}.')

    from banks.models import BankAccount
    bank = BankAccount.nodes.get_or_none(bank_account_id=bank_account_id)
    if not bank:
        raise ValidationError('Bank account not found.')
    bank_gl = bank.gl_account.single()
    if not bank_gl:
        raise ValidationError('Bank account has no linked GL account.')

    ap_acct = invoice.ap_account.single()
    amount = round(amount, 2)

    from journals.models import JournalEntry, JournalLine
    entry = JournalEntry(
        reference=f'APPay-{invoice.invoice_number}',
        date=_to_date(payment_date),
        description=f'Payment for {invoice.invoice_number}',
        status='POSTED',
        entry_type='AP_PAYMENT',
        total_debit=amount,
        total_credit=amount,
        created_by=username,
        approved_by=username,
        approved_at=datetime.utcnow(),
    )
    entry.save()

    dr = JournalLine(side='DEBIT', amount=amount, description='AP payment')
    dr.save()
    entry.lines.connect(dr)
    dr.account.connect(ap_acct)

    cr = JournalLine(side='CREDIT', amount=amount, description='Bank payment')
    cr.save()
    entry.lines.connect(cr)
    cr.account.connect(bank_gl)

    payment = APPayment(
        payment_date=_to_date(payment_date),
        amount=amount,
        reference=reference,
        created_by=username,
    )
    payment.save()
    payment.invoice.connect(invoice)
    payment.bank_account.connect(bank)
    payment.journal_entry.connect(entry)

    from banks.models import BankTransaction
    from banks.services import generate_bank_transaction_reference
    bank_txn = BankTransaction(
        reference=generate_bank_transaction_reference(),
        transaction_type='PAYMENT',
        date=_to_date(payment_date),
        amount=amount,
        description=f'Payment for {invoice.invoice_number}',
        created_by=username,
    )
    bank_txn.save()
    bank_txn.source_bank.connect(bank)
    bank_txn.journal_entry.connect(entry)
    vendor = invoice.vendor.single()
    if vendor:
        bank_txn.vendor.connect(vendor)

    invoice.amount_paid = round(invoice.amount_paid + amount, 2)
    if invoice.amount_paid >= invoice.total_amount - 0.01:
        invoice.status = 'PAID'
    invoice.save()
    return payment
