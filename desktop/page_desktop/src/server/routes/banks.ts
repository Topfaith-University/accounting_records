import crypto from 'crypto';
import { Router } from 'express';
import multer from 'multer';
import { parse } from 'csv-parse/sync';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { requireActiveCompany } from '../middleware/legacyRbac';
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
import { computeBankCurrentBalance, createBankTransaction, getBankGlLines, ServiceError } from '../services/banks.service';
import { sendXlsx } from '../exports/xlsx';
import { sendTablePdf } from '../exports/pdf';

const upload = multer({ storage: multer.memoryStorage() });

async function serializeBankAccount(db: Kysely<Database>, b: any) {
  return {
    bank_account_id: b.bank_account_id,
    name: b.name,
    account_number: b.account_number ?? '',
    bank_name: b.bank_name,
    currency: b.currency,
    opening_balance: b.opening_balance,
    opening_balance_date: b.opening_balance_date,
    is_active: !!b.is_active,
    gl_account_id: b.gl_account_id,
    current_balance: await computeBankCurrentBalance(db, b.bank_account_id, b.company_id),
    created_at: b.created_at,
    updated_at: b.updated_at,
  };
}

function serializeReconciliation(r: any) {
  return {
    reconciliation_id: r.reconciliation_id,
    period_start: r.period_start,
    period_end: r.period_end,
    statement_balance: r.statement_balance,
    status: r.status,
    created_by: r.created_by,
    completed_at: r.completed_at,
    created_at: r.created_at,
    bank_account_id: r.bank_account_id,
  };
}

async function serializeTransaction(db: Kysely<Database>, t: any) {
  const [sourceBank, destBank, vendor, customer] = await Promise.all([
    db.selectFrom('bank_accounts').select('name').where('bank_account_id', '=', t.source_bank_id).executeTakeFirst(),
    t.destination_bank_id ? db.selectFrom('bank_accounts').select('name').where('bank_account_id', '=', t.destination_bank_id).executeTakeFirst() : null,
    t.vendor_id ? db.selectFrom('vendors').select('name').where('vendor_id', '=', t.vendor_id).executeTakeFirst() : null,
    t.customer_id ? db.selectFrom('customers').select('name').where('customer_id', '=', t.customer_id).executeTakeFirst() : null,
  ]);
  const lines = await db
    .selectFrom('journal_lines')
    .innerJoin('accounts', 'accounts.account_id', 'journal_lines.account_id')
    .where('journal_lines.entry_id', '=', t.journal_entry_id)
    .select(['journal_lines.line_id as line_id', 'accounts.account_id as account_id', 'accounts.code as account_code', 'accounts.name as account_name', 'journal_lines.side as side', 'journal_lines.amount as amount', 'journal_lines.description as description'])
    .execute();
  return {
    transaction_id: t.transaction_id,
    reference: t.reference,
    transaction_type: t.transaction_type,
    date: t.date,
    amount: t.amount,
    description: t.description,
    created_by: t.created_by,
    created_at: t.created_at,
    source_bank_name: sourceBank?.name ?? null,
    destination_bank_name: destBank?.name ?? null,
    vendor_name: vendor?.name ?? null,
    customer_name: customer?.name ?? null,
    entry_id: t.journal_entry_id,
    lines,
  };
}

export function banksRouter(db: Kysely<Database>): Router {
  const accounts = Router();
  accounts.use(requireAuth);

  accounts.get('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const rows = await db.selectFrom('bank_accounts').selectAll().where('company_id', '=', companyId).where('is_active', '=', 1).execute();
    res.json(await Promise.all(rows.map((r) => serializeBankAccount(db, r))));
  });

  accounts.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('bank_accounts').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const serialized = await Promise.all(rows.map((r) => serializeBankAccount(db, r)));
    const headers = ['Name', 'Bank', 'Account No.', 'Opening Balance (N)', 'Current Balance (N)'];
    const dataRows = serialized.map((r) => [r.name, r.bank_name, r.account_number, r.opening_balance, r.current_balance]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'bank-accounts', 'Bank Accounts', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'bank-accounts', 'Bank Accounts', headers, dataRows, companyName);
  });

  accounts.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const bank = await db.selectFrom('bank_accounts').selectAll().where('bank_account_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!bank) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeBankAccount(db, bank));
  });

  accounts.get('/:id/ledger/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const bank = await db.selectFrom('bank_accounts').select('bank_account_id').where('bank_account_id', '=', req.params.id).where('company_id', '=', companyId).executeTakeFirst();
    if (!bank) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const lines = await getBankGlLines(db, req.params.id, companyId);
    res.json({ bank_account_id: req.params.id, lines });
  });

  accounts.get('/:id/reconciliations/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const bank = await db.selectFrom('bank_accounts').select('bank_account_id').where('bank_account_id', '=', req.params.id).where('company_id', '=', companyId).executeTakeFirst();
    if (!bank) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const rows = await db.selectFrom('bank_reconciliations').selectAll().where('bank_account_id', '=', req.params.id).where('company_id', '=', companyId).orderBy('created_at', 'desc').execute();
    res.json(rows.map(serializeReconciliation));
  });

  accounts.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (!body.name || !body.bank_name || !body.opening_balance_date) {
      res.status(400).json({ detail: 'name, bank_name, opening_balance_date are required.' });
      return;
    }
    const bankAccountId = crypto.randomUUID();
    const now = new Date().toISOString();
    const openingBalance = body.opening_balance ?? 0;
    await db
      .insertInto('bank_accounts')
      .values({
        bank_account_id: bankAccountId,
        company_id: companyId,
        name: body.name,
        account_number: body.account_number ?? '',
        bank_name: body.bank_name,
        currency: body.currency ?? 'NGN',
        opening_balance: openingBalance,
        opening_balance_date: body.opening_balance_date,
        gl_account_id: body.gl_account_id_input ?? null,
        is_active: 1,
        updated_at: now,
      })
      .execute();
    if (body.gl_account_id_input && openingBalance) {
      const glAcct = await db.selectFrom('accounts').selectAll().where('account_id', '=', body.gl_account_id_input).where('company_id', '=', companyId).executeTakeFirst();
      if (glAcct) {
        const { postOpeningBalanceEntry } = await import('../services/journalPosting.service');
        await postOpeningBalanceEntry(db, glAcct as any, openingBalance, body.opening_balance_date, req.auth!.username, bankAccountId);
      }
    }
    const bank = await db.selectFrom('bank_accounts').selectAll().where('bank_account_id', '=', bankAccountId).executeTakeFirstOrThrow();
    res.status(201).json(await serializeBankAccount(db, bank));
  });

  accounts.patch('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const bank = await db.selectFrom('bank_accounts').selectAll().where('bank_account_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!bank) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const body = { ...(req.body ?? {}) };
    const newGlAccountId = body.gl_account_id_input;
    delete body.opening_balance;
    delete body.gl_account_id_input;
    delete body.bank_account_id;
    delete body.current_balance;
    delete body.gl_account_id;
    delete body.created_at;
    if ('is_active' in body) body.is_active = body.is_active ? 1 : 0;

    if ('gl_account_id_input' in req.body) {
      body.gl_account_id = newGlAccountId ?? bank.gl_account_id;
    }
    await db.updateTable('bank_accounts').set({ ...body, updated_at: new Date().toISOString() }).where('bank_account_id', '=', req.params.id).execute();

    if (newGlAccountId && bank.opening_balance) {
      const glAcct = await db.selectFrom('accounts').selectAll().where('account_id', '=', newGlAccountId).where('company_id', '=', companyId!).executeTakeFirst();
      if (glAcct) {
        const { postOpeningBalanceEntry } = await import('../services/journalPosting.service');
        await postOpeningBalanceEntry(db, glAcct as any, bank.opening_balance, bank.opening_balance_date, req.auth!.username, bank.bank_account_id);
      }
    }
    const updated = await db.selectFrom('bank_accounts').selectAll().where('bank_account_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeBankAccount(db, updated));
  });

  accounts.delete('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const bank = await db.selectFrom('bank_accounts').select('bank_account_id').where('bank_account_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!bank) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    await db.updateTable('bank_accounts').set({ is_active: 0 }).where('bank_account_id', '=', req.params.id).execute();
    res.status(204).send();
  });

  const reconciliations = Router();
  reconciliations.use(requireAuth);

  reconciliations.get('/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    let query = db.selectFrom('bank_reconciliations').selectAll().where('company_id', '=', companyId);
    const bankAccountId = req.query.bank_account_id as string | undefined;
    if (bankAccountId) query = query.where('bank_account_id', '=', bankAccountId);
    const rows = await query.orderBy('created_at', 'desc').execute();
    res.json(rows.map(serializeReconciliation));
  });

  reconciliations.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const recon = await db.selectFrom('bank_reconciliations').selectAll().where('reconciliation_id', '=', req.params.id).where('company_id', '=', companyId).executeTakeFirst();
    if (!recon) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const bank = await db.selectFrom('bank_accounts').selectAll().where('bank_account_id', '=', recon.bank_account_id).executeTakeFirst();
    const lines = bank ? await getBankGlLines(db, bank.bank_account_id, companyId, recon.reconciliation_id) : [];
    res.json({
      ...serializeReconciliation(recon),
      opening_balance: bank?.opening_balance ?? 0,
      bank_account_name: bank?.name ?? '',
      lines,
    });
  });

  reconciliations.post('/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (!body.bank_account_id) {
      res.status(400).json({ detail: 'bank_account_id is required.' });
      return;
    }
    const bank = await db.selectFrom('bank_accounts').select('bank_account_id').where('bank_account_id', '=', body.bank_account_id).where('company_id', '=', companyId).executeTakeFirst();
    if (!bank) {
      res.status(404).json({ detail: 'Bank account not found.' });
      return;
    }
    const reconciliationId = crypto.randomUUID();
    await db
      .insertInto('bank_reconciliations')
      .values({
        reconciliation_id: reconciliationId,
        company_id: companyId,
        bank_account_id: body.bank_account_id,
        period_start: body.period_start,
        period_end: body.period_end,
        statement_balance: body.statement_balance,
        status: 'DRAFT',
        created_by: req.auth!.username,
        completed_at: null,
      })
      .execute();
    const recon = await db.selectFrom('bank_reconciliations').selectAll().where('reconciliation_id', '=', reconciliationId).executeTakeFirstOrThrow();
    res.status(201).json(serializeReconciliation(recon));
  });

  reconciliations.post('/:id/toggle-line/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const recon = await db.selectFrom('bank_reconciliations').selectAll().where('reconciliation_id', '=', req.params.id).where('company_id', '=', companyId).executeTakeFirst();
    if (!recon) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (recon.status !== 'DRAFT') {
      res.status(400).json({ detail: 'Cannot modify a completed reconciliation.' });
      return;
    }
    const lineId = req.body?.line_id;
    if (!lineId) {
      res.status(400).json({ detail: 'line_id is required.' });
      return;
    }
    const line = await db.selectFrom('journal_lines').select('line_id').where('line_id', '=', lineId).where('company_id', '=', companyId).executeTakeFirst();
    if (!line) {
      res.status(404).json({ detail: 'Journal line not found.' });
      return;
    }
    const existing = await db.selectFrom('reconciliation_lines').select('id').where('reconciliation_id', '=', recon.reconciliation_id).where('journal_line_id', '=', lineId).executeTakeFirst();
    let reconciled: boolean;
    if (existing) {
      await db.deleteFrom('reconciliation_lines').where('id', '=', existing.id).execute();
      reconciled = false;
    } else {
      await db.insertInto('reconciliation_lines').values({ reconciliation_id: recon.reconciliation_id, journal_line_id: lineId }).execute();
      reconciled = true;
    }
    res.json({ line_id: lineId, is_reconciled: reconciled });
  });

  reconciliations.post('/:id/complete/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const recon = await db.selectFrom('bank_reconciliations').selectAll().where('reconciliation_id', '=', req.params.id).where('company_id', '=', companyId).executeTakeFirst();
    if (!recon) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (recon.status !== 'DRAFT') {
      res.status(400).json({ detail: 'Already completed.' });
      return;
    }
    const bank = await db.selectFrom('bank_accounts').select(['opening_balance']).where('bank_account_id', '=', recon.bank_account_id).executeTakeFirst();
    const opening = bank?.opening_balance ?? 0;
    const reconciledLineIds = await db.selectFrom('reconciliation_lines').select('journal_line_id').where('reconciliation_id', '=', recon.reconciliation_id).execute();
    let bookBalance = opening;
    for (const { journal_line_id } of reconciledLineIds) {
      const line = await db.selectFrom('journal_lines').select(['side', 'amount']).where('line_id', '=', journal_line_id).executeTakeFirst();
      if (!line) continue;
      bookBalance += line.side === 'DEBIT' ? line.amount : -line.amount;
    }
    if (Math.abs(Math.round(bookBalance * 100) - Math.round(recon.statement_balance * 100)) > 1) {
      const diff = Math.round((recon.statement_balance - bookBalance) * 100) / 100;
      res.status(400).json({ detail: `Unreconciled difference of ₦${diff.toLocaleString()}. Tick all matching items first.` });
      return;
    }
    await db.updateTable('bank_reconciliations').set({ status: 'COMPLETED', completed_at: new Date().toISOString() }).where('reconciliation_id', '=', recon.reconciliation_id).execute();
    const updated = await db.selectFrom('bank_reconciliations').selectAll().where('reconciliation_id', '=', recon.reconciliation_id).executeTakeFirstOrThrow();
    res.json(serializeReconciliation(updated));
  });

  const transactions = Router();
  transactions.use(requireAuth);

  async function queryTransactions(companyId: string, bankAccountId?: string, dateFrom?: string, dateTo?: string) {
    let query = db.selectFrom('bank_transactions').selectAll().where('company_id', '=', companyId);
    if (bankAccountId) {
      query = query.where((eb) => eb.or([eb('source_bank_id', '=', bankAccountId), eb('destination_bank_id', '=', bankAccountId)]));
    }
    if (dateFrom) query = query.where('date', '>=', dateFrom);
    if (dateTo) query = query.where('date', '<=', dateTo);
    return query.orderBy('created_at', 'desc').execute();
  }

  transactions.get('/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const rows = await queryTransactions(
      companyId,
      (req.query.bank_account_id as string) || undefined,
      (req.query.date_from as string) || undefined,
      (req.query.date_to as string) || undefined,
    );
    res.json(await Promise.all(rows.map((r) => serializeTransaction(db, r))));
  });

  transactions.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const companyName = getActiveCompanyName(req);
    const rows = await queryTransactions(
      companyId,
      (req.query.bank_account_id as string) || undefined,
      (req.query.date_from as string) || undefined,
      (req.query.date_to as string) || undefined,
    );
    const serialized = await Promise.all(rows.map((r) => serializeTransaction(db, r)));
    const headers = ['Reference', 'Date', 'Bank', 'Type', 'Description', 'Amount'];
    const dataRows = serialized.map((r) => [r.reference, r.date, r.source_bank_name ?? '', r.transaction_type, r.description ?? '', r.amount]);
    const fmt = (req.query.format as string) || 'csv';
    if (fmt === 'xlsx') {
      await sendXlsx(res, 'bank-transactions', 'Bank Transactions', headers, dataRows, companyName);
      return;
    }
    const csv = [headers.join(','), ...dataRows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))].join('\n');
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', 'attachment; filename="bank-transactions.csv"');
    res.send(csv);
  });

  transactions.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const txn = await db.selectFrom('bank_transactions').selectAll().where('transaction_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!txn) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeTransaction(db, txn));
  });

  transactions.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (body.transaction_type === 'TRANSFER') {
      if (!body.destination_bank_id) {
        res.status(400).json({ destination_bank_id: 'Required for TRANSFER.' });
        return;
      }
      if (!body.transfer_amount) {
        res.status(400).json({ transfer_amount: 'Required for TRANSFER.' });
        return;
      }
    } else if (!body.splits?.length) {
      res.status(400).json({ splits: 'At least one split is required for RECEIPT/PAYMENT.' });
      return;
    }
    try {
      const txnId = await createBankTransaction(db, {
        companyId,
        transactionType: body.transaction_type,
        date: body.date,
        description: body.description ?? '',
        sourceBankId: body.source_bank_id,
        destinationBankId: body.destination_bank_id,
        splits: body.splits ?? [],
        amount: body.transfer_amount,
        createdBy: req.auth!.username,
        vendorId: body.vendor_id || null,
        customerId: body.customer_id || null,
        reference: body.reference || null,
      });
      const txn = await db.selectFrom('bank_transactions').selectAll().where('transaction_id', '=', txnId).executeTakeFirstOrThrow();
      res.status(201).json(await serializeTransaction(db, txn));
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
    }
  });

  transactions.post('/import/', upload.single('file'), async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
    const bankAccountId = (req.body.bank_account_id || '').trim();
    const defaultAcctId = (req.body.default_account_id || '').trim();
    const dateFormatKey = req.body.date_format || 'dd/mm/yyyy';
    const dateRangeType = req.body.date_range_type || 'ALL';
    const dateFromStr = req.body.date_from || '';
    const dateToStr = req.body.date_to || '';
    const file = req.file;

    if (!bankAccountId || !defaultAcctId || !file) {
      res.status(400).json({ detail: 'bank_account_id, default_account_id, and file are required.' });
      return;
    }

    let dateFrom: string | null = null;
    let dateTo: string | null = null;
    if (dateRangeType === 'DATE_RANGE') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dateFromStr) || !/^\d{4}-\d{2}-\d{2}$/.test(dateToStr)) {
        res.status(400).json({ detail: 'Invalid date_from/date_to.' });
        return;
      }
      dateFrom = dateFromStr;
      dateTo = dateToStr;
    }

    function parseRowDate(str: string): string | null {
      let m: RegExpMatchArray | null;
      if (dateFormatKey === 'yyyy-mm-dd') {
        m = str.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!m) return null;
        return `${m[1]}-${m[2]}-${m[3]}`;
      }
      if (dateFormatKey === 'mm/dd/yyyy') {
        m = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (!m) return null;
        return `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
      }
      m = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
      if (!m) return null;
      return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
    }

    const text = file.buffer.toString('utf8').replace(/^﻿/, '');
    const records: Record<string, string>[] = parse(text, { columns: true, skip_empty_lines: true, trim: true });

    let created = 0;
    let skipped = 0;
    const errors: string[] = [];

    for (let i = 0; i < records.length; i++) {
      const rowNum = i + 2;
      const row = records[i];
      const dateStr = (row['Date'] ?? '').trim();
      const description = (row['Description'] ?? '').trim();
      const amountStr = (row['Amount'] ?? '').trim();

      if (!dateStr && !amountStr) continue;

      const txnDate = parseRowDate(dateStr);
      if (!txnDate) {
        errors.push(`Row ${rowNum}: invalid date "${dateStr}"`);
        skipped++;
        continue;
      }

      const amount = Number(amountStr.replace(/,/g, ''));
      if (Number.isNaN(amount)) {
        errors.push(`Row ${rowNum}: invalid amount "${amountStr}"`);
        skipped++;
        continue;
      }
      if (amount === 0) {
        skipped++;
        continue;
      }
      if (dateFrom && dateTo && (txnDate < dateFrom || txnDate > dateTo)) {
        skipped++;
        continue;
      }

      const txnType = amount > 0 ? 'RECEIPT' : 'PAYMENT';
      try {
        await createBankTransaction(db, {
          companyId,
          transactionType: txnType,
          date: txnDate,
          description,
          sourceBankId: bankAccountId,
          destinationBankId: null,
          splits: [{ account_id: defaultAcctId, amount: Math.abs(amount), description: '' }],
          amount: null,
          createdBy: req.auth!.username,
        });
        created++;
      } catch (e) {
        errors.push(`Row ${rowNum}: ${e instanceof Error ? e.message : 'error'}`);
        skipped++;
      }
    }

    res.json({ created, skipped, errors });
  });

  return Router()
    .use('/accounts', accounts)
    .use('/reconciliations', reconciliations)
    .use('/transactions', transactions);
}
