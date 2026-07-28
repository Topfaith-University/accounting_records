import crypto from 'crypto';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { generateBankTransactionReference, generateInvoiceSettlementReference } from './banks.service';

class ServiceError extends Error {}
export { ServiceError };

/** Mirrors receivables/services.py's post_invoice exactly (PRD §4.10): DEBIT AR
 * control account + CREDIT each revenue account (per line). */
export async function postSalesInvoice(db: Kysely<Database>, invoiceId: string, companyId: string, approver: string): Promise<void> {
  const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', invoiceId).where('company_id', '=', companyId).executeTakeFirst();
  if (!invoice) throw new ServiceError('Invoice not found.');
  if (invoice.status !== 'DRAFT') throw new ServiceError(`Cannot post invoice with status ${invoice.status}.`);

  const lines = await db.selectFrom('sales_invoice_lines').selectAll().where('invoice_id', '=', invoiceId).execute();
  if (!lines.length) throw new ServiceError('Invoice has no lines.');

  const total = Math.round(lines.reduce((s, l) => s + l.amount, 0) * 100) / 100;
  const now = new Date().toISOString();
  const entryId = crypto.randomUUID();

  await db
    .insertInto('journal_entries')
    .values({
      entry_id: entryId,
      company_id: companyId,
      reference: `AR-${invoice.invoice_number}`,
      date: invoice.date,
      description: `Sales Invoice ${invoice.invoice_number}`,
      status: 'POSTED',
      entry_type: 'AR_RECEIPT',
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

  await db
    .insertInto('journal_lines')
    .values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: invoice.ar_account_id, side: 'DEBIT', amount: total, description: `AR — ${invoice.invoice_number}` })
    .execute();
  for (const line of lines) {
    await db
      .insertInto('journal_lines')
      .values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: line.revenue_account_id, side: 'CREDIT', amount: line.amount, description: line.description })
      .execute();
  }

  await db.updateTable('sales_invoices').set({ status: 'POSTED', total_amount: total, journal_entry_id: entryId }).where('invoice_id', '=', invoiceId).execute();
}

export async function voidSalesInvoice(db: Kysely<Database>, invoiceId: string, companyId: string, voider: string): Promise<void> {
  const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', invoiceId).where('company_id', '=', companyId).executeTakeFirst();
  if (!invoice) throw new ServiceError('Invoice not found.');
  if (!['DRAFT', 'POSTED'].includes(invoice.status)) throw new ServiceError(`Cannot void invoice with status ${invoice.status}.`);
  if (invoice.status === 'POSTED' && invoice.journal_entry_id) {
    await db.updateTable('journal_entries').set({ status: 'VOID', voided_by: voider, voided_at: new Date().toISOString() }).where('entry_id', '=', invoice.journal_entry_id).execute();
  }
  await db.updateTable('sales_invoices').set({ status: 'VOID' }).where('invoice_id', '=', invoiceId).execute();
}

/** Mirrors receivables/services.py's record_receipt exactly (PRD §4.10): DEBIT
 * bank GL account + CREDIT AR control account, plus a paired BankTransaction. */
export async function recordArReceipt(
  db: Kysely<Database>,
  invoiceId: string,
  companyId: string,
  receiptDate: string,
  amount: number,
  reference: string,
  bankAccountId: string,
  username: string,
): Promise<string> {
  const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', invoiceId).where('company_id', '=', companyId).executeTakeFirst();
  if (!invoice) throw new ServiceError('Invoice not found.');
  if (invoice.status !== 'POSTED') throw new ServiceError('Can only receive against POSTED invoices.');

  const remaining = Math.round((invoice.total_amount - invoice.amount_received) * 100) / 100;
  if (amount > remaining + 0.01) throw new ServiceError(`Receipt amount ${amount.toFixed(2)} exceeds remaining balance ${remaining.toFixed(2)}.`);

  const bank = await db.selectFrom('bank_accounts').selectAll().where('bank_account_id', '=', bankAccountId).where('company_id', '=', companyId).executeTakeFirst();
  if (!bank) throw new ServiceError('Bank account not found.');
  if (!bank.gl_account_id) throw new ServiceError('Bank account has no linked GL account.');

  amount = Math.round(amount * 100) / 100;
  const now = new Date().toISOString();
  const entryId = crypto.randomUUID();
  const entryReference = await generateInvoiceSettlementReference(db, 'ARRec', invoice.invoice_number, companyId);

  await db
    .insertInto('journal_entries')
    .values({
      entry_id: entryId,
      company_id: companyId,
      reference: entryReference,
      date: receiptDate,
      description: `Receipt for ${invoice.invoice_number}`,
      status: 'POSTED',
      entry_type: 'AR_RECEIPT',
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
  await db.insertInto('journal_lines').values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: bank.gl_account_id, side: 'DEBIT', amount, description: 'Bank receipt' }).execute();
  await db.insertInto('journal_lines').values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: invoice.ar_account_id, side: 'CREDIT', amount, description: 'AR receipt' }).execute();

  const receiptId = crypto.randomUUID();
  await db
    .insertInto('ar_receipts')
    .values({ receipt_id: receiptId, company_id: companyId, invoice_id: invoiceId, receipt_date: receiptDate, amount, reference, bank_account_id: bankAccountId, journal_entry_id: entryId, created_by: username })
    .execute();

  const bankTxnReference = await generateBankTransactionReference(db, companyId);
  await db
    .insertInto('bank_transactions')
    .values({
      transaction_id: crypto.randomUUID(),
      company_id: companyId,
      reference: bankTxnReference,
      transaction_type: 'RECEIPT',
      date: receiptDate,
      amount,
      description: `Receipt for ${invoice.invoice_number}`,
      source_bank_id: bankAccountId,
      destination_bank_id: null,
      journal_entry_id: entryId,
      vendor_id: null,
      customer_id: invoice.customer_id,
      created_by: username,
      updated_at: now,
    })
    .execute();

  const newAmountReceived = Math.round((invoice.amount_received + amount) * 100) / 100;
  const newStatus = newAmountReceived >= invoice.total_amount - 0.01 ? 'PAID' : invoice.status;
  await db.updateTable('sales_invoices').set({ amount_received: newAmountReceived, status: newStatus }).where('invoice_id', '=', invoiceId).execute();

  return receiptId;
}

interface StatementLine {
  date: string;
  type: 'INVOICE' | 'RECEIPT';
  reference: string;
  description: string;
  debit: number;
  credit: number;
  running_balance: number;
}

/** Mirrors receivables/services.py's get_customer_statement exactly (PRD §4.18). */
export async function getCustomerStatement(db: Kysely<Database>, customerId: string, companyId: string) {
  const customer = await db.selectFrom('customers').selectAll().where('customer_id', '=', customerId).where('company_id', '=', companyId).executeTakeFirst();
  if (!customer) return null;

  const invoices = await db
    .selectFrom('sales_invoices')
    .selectAll()
    .where('customer_id', '=', customerId)
    .where('company_id', '=', companyId)
    .where('status', 'in', ['POSTED', 'PAID'])
    .execute();

  const events: { date: string; type: 'INVOICE' | 'RECEIPT'; reference: string; description: string; debit: number; credit: number }[] = [];
  for (const invoice of invoices) {
    events.push({
      date: invoice.date,
      type: 'INVOICE',
      reference: invoice.invoice_number,
      description: invoice.description || `Invoice ${invoice.invoice_number}`,
      debit: Math.round(invoice.total_amount * 100) / 100,
      credit: 0,
    });
    const receipts = await db.selectFrom('ar_receipts').selectAll().where('invoice_id', '=', invoice.invoice_id).execute();
    for (const receipt of receipts) {
      events.push({
        date: receipt.receipt_date,
        type: 'RECEIPT',
        reference: receipt.reference || '',
        description: `Receipt for ${invoice.invoice_number}`,
        debit: 0,
        credit: Math.round(receipt.amount * 100) / 100,
      });
    }
  }
  events.sort((a, b) => (a.date === b.date ? (a.type === 'INVOICE' ? -1 : 1) - (b.type === 'INVOICE' ? -1 : 1) : a.date < b.date ? -1 : 1));

  let runningBalance = 0;
  const lines: StatementLine[] = events.map((e) => {
    runningBalance += e.debit - e.credit;
    return { ...e, running_balance: Math.round(runningBalance * 100) / 100 };
  });

  return { entity_id: customer.customer_id, entity_name: customer.name, lines, closing_balance: Math.round(runningBalance * 100) / 100 };
}
