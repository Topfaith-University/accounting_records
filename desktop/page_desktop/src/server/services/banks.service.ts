import crypto from 'crypto';
import { Kysely } from 'kysely';
import { Database } from '../db/types';

class ServiceError extends Error {}
export { ServiceError };

/** Mirrors banks/services.py's compute_bank_current_balance exactly: opening
 * balance + this bank's own BankTransaction movements only — deliberately
 * independent of the GL account balance (PRD's banks.service.ts entry). */
export async function computeBankCurrentBalance(db: Kysely<Database>, bankAccountId: string, companyId: string): Promise<number> {
  const bank = await db
    .selectFrom('bank_accounts')
    .select('opening_balance')
    .where('bank_account_id', '=', bankAccountId)
    .where('company_id', '=', companyId)
    .executeTakeFirst();
  if (!bank) return 0;

  const sourceTxns = await db
    .selectFrom('bank_transactions')
    .select(['transaction_type', 'amount'])
    .where('source_bank_id', '=', bankAccountId)
    .where('company_id', '=', companyId)
    .execute();
  const sourceMovement = sourceTxns.reduce((s, t) => s + (t.transaction_type === 'RECEIPT' ? t.amount : -t.amount), 0);

  const destTxns = await db
    .selectFrom('bank_transactions')
    .select('amount')
    .where('destination_bank_id', '=', bankAccountId)
    .where('company_id', '=', companyId)
    .where('transaction_type', '=', 'TRANSFER')
    .execute();
  const destMovement = destTxns.reduce((s, t) => s + t.amount, 0);

  return Math.round((bank.opening_balance + sourceMovement + destMovement) * 100) / 100;
}

/** Mirrors banks/services.py's get_bank_gl_lines. */
export async function getBankGlLines(db: Kysely<Database>, bankAccountId: string, companyId: string, reconId?: string) {
  const bank = await db
    .selectFrom('bank_accounts')
    .select('gl_account_id')
    .where('bank_account_id', '=', bankAccountId)
    .where('company_id', '=', companyId)
    .executeTakeFirst();
  if (!bank || !bank.gl_account_id) return [];

  const rows = await db
    .selectFrom('journal_lines')
    .innerJoin('journal_entries', 'journal_entries.entry_id', 'journal_lines.entry_id')
    .where('journal_lines.account_id', '=', bank.gl_account_id)
    .where('journal_entries.company_id', '=', companyId)
    .where('journal_entries.status', '=', 'POSTED')
    .select([
      'journal_lines.line_id as line_id',
      'journal_entries.entry_id as entry_id',
      'journal_entries.reference as reference',
      'journal_entries.date as date',
      'journal_entries.description as entry_description',
      'journal_lines.side as side',
      'journal_lines.amount as amount',
      'journal_lines.description as line_description',
    ])
    .orderBy('journal_entries.date', 'asc')
    .execute();

  let reconciledIds = new Set<string>();
  if (reconId) {
    const reconciled = await db.selectFrom('reconciliation_lines').select('journal_line_id').where('reconciliation_id', '=', reconId).execute();
    reconciledIds = new Set(reconciled.map((r) => r.journal_line_id));
  }
  return rows.map((r) => ({ ...r, is_reconciled: reconciledIds.has(r.line_id) }));
}

/** Mirrors banks/services.py's generate_bank_transaction_reference — atomic
 * per-year counter (PRD §4.8). */
export async function generateBankTransactionReference(db: Kysely<Database>, companyId: string): Promise<string> {
  const year = new Date().getFullYear();
  await db
    .insertInto('bank_txn_counters')
    .values({ company_id: companyId, year, seq: 1 })
    .onConflict((oc) => oc.columns(['company_id', 'year']).doUpdateSet((eb) => ({ seq: eb('bank_txn_counters.seq', '+', 1) })))
    .execute();
  const row = await db
    .selectFrom('bank_txn_counters')
    .select('seq')
    .where('company_id', '=', companyId)
    .where('year', '=', year)
    .executeTakeFirstOrThrow();
  return `BT-${year}-${String(row.seq).padStart(4, '0')}`;
}

/** Mirrors banks/services.py's generate_invoice_settlement_reference — atomic
 * per-(prefix,invoice_number) counter (PRD §4.8). */
export async function generateInvoiceSettlementReference(
  db: Kysely<Database>,
  prefix: string,
  invoiceNumber: string,
  companyId: string,
): Promise<string> {
  await db
    .insertInto('invoice_settlement_counters')
    .values({ company_id: companyId, prefix, invoice_number: invoiceNumber, seq: 1 })
    .onConflict((oc) =>
      oc.columns(['company_id', 'prefix', 'invoice_number']).doUpdateSet((eb) => ({ seq: eb('invoice_settlement_counters.seq', '+', 1) })),
    )
    .execute();
  const row = await db
    .selectFrom('invoice_settlement_counters')
    .select('seq')
    .where('company_id', '=', companyId)
    .where('prefix', '=', prefix)
    .where('invoice_number', '=', invoiceNumber)
    .executeTakeFirstOrThrow();
  return `${prefix}-${invoiceNumber}-${String(row.seq).padStart(4, '0')}`;
}

interface Split {
  account_id: string;
  amount: number;
  description?: string;
}

/** Mirrors banks/services.py's create_bank_transaction exactly (PRD §4.7):
 * shared path for manual entry, CSV import, and AP/AR auto-generated
 * transactions. RECEIPT/PAYMENT post the bank's GL line + one or more split
 * lines on the contra side; TRANSFER posts a simple two-line entry between
 * two banks' GL accounts. */
export async function createBankTransaction(
  db: Kysely<Database>,
  params: {
    companyId: string;
    transactionType: 'RECEIPT' | 'PAYMENT' | 'TRANSFER';
    date: string;
    description: string;
    sourceBankId: string;
    destinationBankId?: string | null;
    splits: Split[];
    amount?: number | null;
    createdBy: string;
    vendorId?: string | null;
    customerId?: string | null;
    reference?: string | null;
  },
): Promise<string> {
  const { companyId } = params;
  const VALID_TYPES = new Set(['RECEIPT', 'PAYMENT', 'TRANSFER']);
  if (!VALID_TYPES.has(params.transactionType)) throw new ServiceError('transaction_type must be one of PAYMENT, RECEIPT, TRANSFER.');

  const sourceBank = await db
    .selectFrom('bank_accounts')
    .selectAll()
    .where('bank_account_id', '=', params.sourceBankId)
    .where('company_id', '=', companyId)
    .executeTakeFirst();
  if (!sourceBank) throw new ServiceError('Source bank account not found.');
  if (!sourceBank.gl_account_id) {
    throw new ServiceError(`Bank account "${sourceBank.name}" has no linked GL account. Edit the bank account and assign a GL account before posting transactions.`);
  }

  let destBank: typeof sourceBank | undefined;
  let totalAmount = 0;
  let resolvedSplits: { accountId: string; amount: number; description: string }[] = [];

  if (params.transactionType === 'TRANSFER') {
    if (!params.destinationBankId) throw new ServiceError('destination_bank_id is required for TRANSFER.');
    if (params.destinationBankId === params.sourceBankId) throw new ServiceError('Source and destination bank accounts must differ.');
    destBank = await db
      .selectFrom('bank_accounts')
      .selectAll()
      .where('bank_account_id', '=', params.destinationBankId)
      .where('company_id', '=', companyId)
      .executeTakeFirst();
    if (!destBank) throw new ServiceError('Destination bank account not found.');
    if (!destBank.gl_account_id) {
      throw new ServiceError(`Bank account "${destBank.name}" has no linked GL account. Edit the bank account and assign a GL account before posting transactions.`);
    }
    const amt = Number(params.amount);
    if (Number.isNaN(amt)) throw new ServiceError('Amount must be a valid number for TRANSFER.');
    if (amt <= 0) throw new ServiceError('Amount must be positive for TRANSFER.');
    totalAmount = amt;
  } else {
    if (!params.splits?.length) throw new ServiceError('At least one split is required.');
    for (const split of params.splits) {
      const amt = Number(split.amount);
      if (Number.isNaN(amt)) throw new ServiceError('Split amount must be a valid number.');
      if (amt <= 0) throw new ServiceError('Each split amount must be positive.');
      const acct = await db.selectFrom('accounts').select('account_id').where('account_id', '=', split.account_id).where('company_id', '=', companyId).executeTakeFirst();
      if (!acct) throw new ServiceError(`Account ${split.account_id} not found.`);
      resolvedSplits.push({ accountId: split.account_id, amount: amt, description: split.description ?? '' });
    }
    totalAmount = resolvedSplits.reduce((s, x) => s + x.amount, 0);
  }

  const reference = params.reference || (await generateBankTransactionReference(db, companyId));
  const now = new Date().toISOString();
  const entryId = crypto.randomUUID();

  await db
    .insertInto('journal_entries')
    .values({
      entry_id: entryId,
      company_id: companyId,
      reference,
      date: params.date,
      description: params.description,
      status: 'POSTED',
      entry_type: 'BANK_TRANSACTION',
      total_debit: totalAmount,
      total_credit: totalAmount,
      period_id: null,
      created_by: params.createdBy,
      approved_by: params.createdBy,
      approved_at: now,
      voided_by: '',
      voided_at: null,
      updated_at: now,
    })
    .execute();

  async function addLine(side: 'DEBIT' | 'CREDIT', amount: number, accountId: string, description: string) {
    await db
      .insertInto('journal_lines')
      .values({ line_id: crypto.randomUUID(), company_id: companyId, entry_id: entryId, account_id: accountId, side, amount, description })
      .execute();
  }

  if (params.transactionType === 'TRANSFER') {
    await addLine('CREDIT', totalAmount, sourceBank.gl_account_id!, params.description);
    await addLine('DEBIT', totalAmount, destBank!.gl_account_id!, params.description);
  } else {
    const bankSide = params.transactionType === 'RECEIPT' ? 'DEBIT' : 'CREDIT';
    await addLine(bankSide, totalAmount, sourceBank.gl_account_id!, params.description);
    const contraSide = params.transactionType === 'RECEIPT' ? 'CREDIT' : 'DEBIT';
    for (const split of resolvedSplits) {
      await addLine(contraSide, split.amount, split.accountId, split.description);
    }
  }

  const txnId = crypto.randomUUID();
  await db
    .insertInto('bank_transactions')
    .values({
      transaction_id: txnId,
      company_id: companyId,
      reference,
      transaction_type: params.transactionType,
      date: params.date,
      amount: totalAmount,
      description: params.description,
      source_bank_id: params.sourceBankId,
      destination_bank_id: params.transactionType === 'TRANSFER' ? params.destinationBankId! : null,
      journal_entry_id: entryId,
      vendor_id: params.vendorId ?? null,
      customer_id: params.customerId ?? null,
      created_by: params.createdBy,
      updated_at: now,
    })
    .execute();

  return txnId;
}
