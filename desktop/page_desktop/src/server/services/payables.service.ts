import crypto from 'crypto';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { generateBankTransactionReference, generateInvoiceSettlementReference } from './banks.service';

class ServiceError extends Error {}
export { ServiceError };

export async function nextInvoiceNumber(db: Kysely<Database>, prefix: string, table: 'purchase_invoices' | 'sales_invoices', companyId: string): Promise<string> {
  const year = new Date().getFullYear();
  const pattern = `${prefix}-${year}-`;
  const rows = await db
    .selectFrom(table)
    .select('invoice_number')
    .where('company_id', '=', companyId)
    .where('invoice_number', 'like', `${pattern}%`)
    .orderBy('invoice_number', 'desc')
    .limit(1)
    .execute();
  let num = 1;
  if (rows.length) {
    const suffix = rows[0].invoice_number.split('-').pop() ?? '';
    const parsed = parseInt(suffix, 10);
    if (!Number.isNaN(parsed)) num = parsed + 1;
  }
  return `${prefix}-${year}-${String(num).padStart(4, '0')}`;
}

/** Mirrors payables/services.py's post_invoice exactly (PRD §4.9): DEBIT each
 * expense account (per line) + CREDIT AP control account. */
export async function postPurchaseInvoice(db: Kysely<Database>, invoiceId: string, companyId: string, approver: string): Promise<void> {
  const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', invoiceId).where('company_id', '=', companyId).executeTakeFirst();
  if (!invoice) throw new ServiceError('Invoice not found.');
  if (invoice.status !== 'DRAFT') throw new ServiceError(`Cannot post invoice with status ${invoice.status}.`);

  const lines = await db.selectFrom('purchase_invoice_lines').selectAll().where('invoice_id', '=', invoiceId).execute();
  if (!lines.length) throw new ServiceError('Invoice has no lines.');

  const total = Math.round(lines.reduce((s, l) => s + l.amount, 0) * 100) / 100;
  const now = new Date().toISOString();
  const entryId = crypto.randomUUID();

  await db
    .insertInto('journal_entries')
    .values({
      entry_id: entryId,
      company_id: companyId,
      reference: `AP-${invoice.invoice_number}`,
      date: invoice.date,
      description: `Purchase Invoice ${invoice.invoice_number}`,
      status: 'POSTED',
      entry_type: 'AP_PAYMENT',
      total_debit: total,
      total_credit: total,
      period_id: null,
      created_by: approver,
      approved_by: approver,
      approved_at: now,
      voided_by: '',
      voided_at: null,
      updated_at: now,
    })
    .execute();

  for (const line of lines) {
    await db
      .insertInto('journal_lines')
      .values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: line.expense_account_id, side: 'DEBIT', amount: line.amount, description: line.description })
      .execute();
  }
  await db
    .insertInto('journal_lines')
    .values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: invoice.ap_account_id, side: 'CREDIT', amount: total, description: `AP — ${invoice.invoice_number}` })
    .execute();

  await db.updateTable('purchase_invoices').set({ status: 'POSTED', total_amount: total, journal_entry_id: entryId }).where('invoice_id', '=', invoiceId).execute();
}

export async function voidPurchaseInvoice(db: Kysely<Database>, invoiceId: string, companyId: string, voider: string): Promise<void> {
  const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', invoiceId).where('company_id', '=', companyId).executeTakeFirst();
  if (!invoice) throw new ServiceError('Invoice not found.');
  if (!['DRAFT', 'POSTED'].includes(invoice.status)) throw new ServiceError(`Cannot void invoice with status ${invoice.status}.`);
  if (invoice.status === 'POSTED' && invoice.journal_entry_id) {
    await db.updateTable('journal_entries').set({ status: 'VOID', voided_by: voider, voided_at: new Date().toISOString() }).where('entry_id', '=', invoice.journal_entry_id).execute();
  }
  await db.updateTable('purchase_invoices').set({ status: 'VOID' }).where('invoice_id', '=', invoiceId).execute();
}

/** Mirrors payables/services.py's record_payment exactly (PRD §4.9): DEBIT AP
 * control account + CREDIT bank GL account, plus a paired BankTransaction. */
export async function recordApPayment(
  db: Kysely<Database>,
  invoiceId: string,
  companyId: string,
  paymentDate: string,
  amount: number,
  reference: string,
  bankAccountId: string,
  username: string,
): Promise<string> {
  const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', invoiceId).where('company_id', '=', companyId).executeTakeFirst();
  if (!invoice) throw new ServiceError('Invoice not found.');
  if (invoice.status !== 'POSTED') throw new ServiceError('Can only pay POSTED invoices.');

  const remaining = Math.round((invoice.total_amount - invoice.amount_paid) * 100) / 100;
  if (amount > remaining + 0.01) throw new ServiceError(`Payment amount ${amount.toFixed(2)} exceeds remaining balance ${remaining.toFixed(2)}.`);

  const bank = await db.selectFrom('bank_accounts').selectAll().where('bank_account_id', '=', bankAccountId).where('company_id', '=', companyId).executeTakeFirst();
  if (!bank) throw new ServiceError('Bank account not found.');
  if (!bank.gl_account_id) throw new ServiceError('Bank account has no linked GL account.');

  amount = Math.round(amount * 100) / 100;
  const now = new Date().toISOString();
  const entryId = crypto.randomUUID();
  const entryReference = await generateInvoiceSettlementReference(db, 'APPay', invoice.invoice_number, companyId);

  await db
    .insertInto('journal_entries')
    .values({
      entry_id: entryId,
      company_id: companyId,
      reference: entryReference,
      date: paymentDate,
      description: `Payment for ${invoice.invoice_number}`,
      status: 'POSTED',
      entry_type: 'AP_PAYMENT',
      total_debit: amount,
      total_credit: amount,
      period_id: null,
      created_by: username,
      approved_by: username,
      approved_at: now,
      voided_by: '',
      voided_at: null,
      updated_at: now,
    })
    .execute();
  await db.insertInto('journal_lines').values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: invoice.ap_account_id, side: 'DEBIT', amount, description: 'AP payment' }).execute();
  await db.insertInto('journal_lines').values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: bank.gl_account_id, side: 'CREDIT', amount, description: 'Bank payment' }).execute();

  const paymentId = crypto.randomUUID();
  await db
    .insertInto('ap_payments')
    .values({ payment_id: paymentId, company_id: companyId, invoice_id: invoiceId, payment_date: paymentDate, amount, reference, bank_account_id: bankAccountId, journal_entry_id: entryId, created_by: username })
    .execute();

  const bankTxnReference = await generateBankTransactionReference(db, companyId);
  await db
    .insertInto('bank_transactions')
    .values({
      transaction_id: crypto.randomUUID(),
      company_id: companyId,
      reference: bankTxnReference,
      transaction_type: 'PAYMENT',
      date: paymentDate,
      amount,
      description: `Payment for ${invoice.invoice_number}`,
      source_bank_id: bankAccountId,
      destination_bank_id: null,
      journal_entry_id: entryId,
      vendor_id: invoice.vendor_id,
      customer_id: null,
      created_by: username,
      updated_at: now,
    })
    .execute();

  const newAmountPaid = Math.round((invoice.amount_paid + amount) * 100) / 100;
  const newStatus = newAmountPaid >= invoice.total_amount - 0.01 ? 'PAID' : invoice.status;
  await db.updateTable('purchase_invoices').set({ amount_paid: newAmountPaid, status: newStatus }).where('invoice_id', '=', invoiceId).execute();

  return paymentId;
}

interface StatementLine {
  date: string;
  type: 'INVOICE' | 'PAYMENT';
  reference: string;
  description: string;
  debit: number;
  credit: number;
  running_balance: number;
}

/** Mirrors payables/services.py's get_vendor_statement exactly (PRD §4.18). */
export async function getVendorStatement(db: Kysely<Database>, vendorId: string, companyId: string) {
  const vendor = await db.selectFrom('vendors').selectAll().where('vendor_id', '=', vendorId).where('company_id', '=', companyId).executeTakeFirst();
  if (!vendor) return null;

  const invoices = await db
    .selectFrom('purchase_invoices')
    .selectAll()
    .where('vendor_id', '=', vendorId)
    .where('company_id', '=', companyId)
    .where('status', 'in', ['POSTED', 'PAID'])
    .execute();

  const events: { date: string; type: 'INVOICE' | 'PAYMENT'; reference: string; description: string; debit: number; credit: number }[] = [];
  for (const invoice of invoices) {
    events.push({
      date: invoice.date,
      type: 'INVOICE',
      reference: invoice.invoice_number,
      description: invoice.description || `Invoice ${invoice.invoice_number}`,
      debit: 0,
      credit: Math.round(invoice.total_amount * 100) / 100,
    });
    const payments = await db.selectFrom('ap_payments').selectAll().where('invoice_id', '=', invoice.invoice_id).execute();
    for (const payment of payments) {
      events.push({
        date: payment.payment_date,
        type: 'PAYMENT',
        reference: payment.reference || '',
        description: `Payment for ${invoice.invoice_number}`,
        debit: Math.round(payment.amount * 100) / 100,
        credit: 0,
      });
    }
  }
  events.sort((a, b) => (a.date === b.date ? (a.type === 'INVOICE' ? -1 : 1) - (b.type === 'INVOICE' ? -1 : 1) : a.date < b.date ? -1 : 1));

  let runningBalance = 0;
  const lines: StatementLine[] = events.map((e) => {
    runningBalance += e.credit - e.debit;
    return { ...e, running_balance: Math.round(runningBalance * 100) / 100 };
  });

  return { entity_id: vendor.vendor_id, entity_name: vendor.name, lines, closing_balance: Math.round(runningBalance * 100) / 100 };
}
