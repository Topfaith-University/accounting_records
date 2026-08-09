from datetime import datetime, date as _date
from django.utils import timezone

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import PurchaseInvoice, APPayment, Vendor


def _to_date(val):
    if isinstance(val, _date):
        return val
    return _date.fromisoformat(str(val))


@transaction.atomic
def post_invoice(invoice_id: str, company_id: str, approver) -> PurchaseInvoice:
    invoice = (
        PurchaseInvoice.objects
        .filter(invoice_id=invoice_id, company_id=company_id)
        .select_related('ap_account')
        .select_for_update()
        .first()
    )
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status != 'DRAFT':
        raise ValidationError(f'Cannot post invoice with status {invoice.status}.')

    lines = list(invoice.lines.select_related('expense_account').all())
    if not lines:
        raise ValidationError('Invoice has no lines.')

    total = round(sum(l.amount for l in lines), 2)
    ap_acct = invoice.ap_account
    if not ap_acct:
        raise ValidationError('AP control account not set on invoice.')

    from journals.models import JournalEntry, JournalLine
    entry = JournalEntry.objects.create(
        company_id=company_id,
        reference=f'AP-{invoice.invoice_number}',
        date=_to_date(invoice.date),
        description=f'Purchase Invoice {invoice.invoice_number}',
        status='POSTED',
        entry_type='AP_PAYMENT',
        total_debit=total,
        total_credit=total,
        created_by=approver,
        approved_by=approver,
        approved_at=timezone.now(),
    )

    for line in lines:
        expense_acct = line.expense_account
        if not expense_acct:
            raise ValidationError(f'Line {line.line_id} has no expense account.')
        JournalLine.objects.create(
            company_id=company_id, entry=entry, account=expense_acct,
            side='DEBIT', amount=line.amount, description=line.description,
        )

    JournalLine.objects.create(
        company_id=company_id, entry=entry, account=ap_acct,
        side='CREDIT', amount=total, description=f'AP — {invoice.invoice_number}',
    )

    invoice.journal_entry = entry
    invoice.status = 'POSTED'
    invoice.total_amount = total
    invoice.save()
    return invoice


@transaction.atomic
def void_invoice(invoice_id: str, company_id: str, voider) -> PurchaseInvoice:
    invoice = (
        PurchaseInvoice.objects
        .filter(invoice_id=invoice_id, company_id=company_id)
        .select_for_update()
        .first()
    )
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status not in ('DRAFT', 'POSTED'):
        raise ValidationError(f'Cannot void invoice with status {invoice.status}.')
    if invoice.status == 'POSTED' and invoice.journal_entry:
        je = invoice.journal_entry
        je.status = 'VOID'
        je.voided_by = voider
        je.voided_at = timezone.now()
        je.save()
    invoice.status = 'VOID'
    invoice.save()
    return invoice


@transaction.atomic
def record_payment(invoice_id: str, company_id: str, payment_date, amount: float,
                   reference: str, bank_account_id: str, user) -> APPayment:
    invoice = (
        PurchaseInvoice.objects
        .filter(invoice_id=invoice_id, company_id=company_id)
        .select_related('ap_account', 'vendor')
        .select_for_update()
        .first()
    )
    if not invoice:
        raise ValidationError('Invoice not found.')
    if invoice.status != 'POSTED':
        raise ValidationError('Can only pay POSTED invoices.')

    remaining = round(invoice.total_amount - invoice.amount_paid, 2)
    if amount > remaining + 0.01:
        raise ValidationError(f'Payment amount {amount:.2f} exceeds remaining balance {remaining:.2f}.')

    from banks.models import BankAccount
    bank = BankAccount.objects.filter(bank_account_id=bank_account_id, company_id=company_id).select_related('gl_account').first()
    if not bank:
        raise ValidationError('Bank account not found.')
    bank_gl = bank.gl_account
    if not bank_gl:
        raise ValidationError('Bank account has no linked GL account.')

    ap_acct = invoice.ap_account
    amount = round(amount, 2)

    from journals.models import JournalEntry, JournalLine
    from banks.services import (
        generate_bank_transaction_reference,
        generate_invoice_settlement_reference,
    )
    entry = JournalEntry.objects.create(
        company_id=company_id,
        reference=generate_invoice_settlement_reference('APPay', invoice.invoice_number, company_id),
        date=_to_date(payment_date),
        description=f'Payment for {invoice.invoice_number}',
        status='POSTED',
        entry_type='AP_PAYMENT',
        total_debit=amount,
        total_credit=amount,
        created_by=user,
        approved_by=user,
        approved_at=timezone.now(),
    )

    JournalLine.objects.create(
        company_id=company_id, entry=entry, account=ap_acct,
        side='DEBIT', amount=amount, description='AP payment',
    )
    JournalLine.objects.create(
        company_id=company_id, entry=entry, account=bank_gl,
        side='CREDIT', amount=amount, description='Bank payment',
    )

    payment = APPayment.objects.create(
        company_id=company_id,
        payment_date=_to_date(payment_date),
        amount=amount,
        reference=reference,
        created_by=user,
        invoice=invoice,
        bank_account=bank,
        journal_entry=entry,
    )

    from banks.models import BankTransaction
    BankTransaction.objects.create(
        company_id=company_id,
        reference=generate_bank_transaction_reference(company_id),
        transaction_type='PAYMENT',
        date=_to_date(payment_date),
        amount=amount,
        description=f'Payment for {invoice.invoice_number}',
        created_by=user,
        source_bank=bank,
        journal_entry=entry,
        vendor=invoice.vendor,
    )

    invoice.amount_paid = round(invoice.amount_paid + amount, 2)
    if invoice.amount_paid >= invoice.total_amount - 0.01:
        invoice.status = 'PAID'
    invoice.save()
    return payment


def get_vendor_statement(vendor_id: str, company_id: str) -> dict | None:
    vendor = Vendor.objects.filter(vendor_id=vendor_id, company_id=company_id).first()
    if not vendor:
        return None

    invoices = vendor.invoices.filter(status__in=('POSTED', 'PAID')).prefetch_related('payments')

    events = []
    for invoice in invoices:
        events.append({
            'date': invoice.date,
            'type': 'INVOICE',
            'reference': invoice.invoice_number,
            'description': invoice.description or f'Invoice {invoice.invoice_number}',
            'debit': 0.0,
            'credit': round(invoice.total_amount, 2),
        })
        for payment in invoice.payments.all():
            events.append({
                'date': payment.payment_date,
                'type': 'PAYMENT',
                'reference': payment.reference or '',
                'description': f'Payment for {invoice.invoice_number}',
                'debit': round(payment.amount, 2),
                'credit': 0.0,
            })

    events.sort(key=lambda e: (str(e['date']), 0 if e['type'] == 'INVOICE' else 1))

    running_balance = 0.0
    lines = []
    for e in events:
        running_balance += e['credit'] - e['debit']
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
        'entity_id': vendor.vendor_id,
        'entity_name': vendor.name,
        'lines': lines,
        'closing_balance': round(running_balance, 2),
    }
