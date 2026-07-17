import crypto from 'crypto';
import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { requireActiveCompany, requireLegacyGroup } from '../middleware/legacyRbac';
import { getActiveCompanyId } from '../lib/rbac';
import { addDays, addMonthsClamped, monthYearLabel } from '../lib/dates';
import { generateJournalEntryReference, postJournalEntry, ServiceError, voidJournalEntry } from '../services/journals.service';
import { userHasAnyGroup } from '../lib/rbac';
import { sendXlsx } from '../exports/xlsx';
import { sendTablePdf } from '../exports/pdf';

function serializeEntry(e: any) {
  return {
    entry_id: e.entry_id,
    reference: e.reference,
    date: e.date,
    description: e.description,
    status: e.status,
    entry_type: e.entry_type,
    total_debit: e.total_debit,
    total_credit: e.total_credit,
    created_by: e.created_by,
    approved_by: e.approved_by,
    approved_at: e.approved_at,
    voided_by: e.voided_by,
    voided_at: e.voided_at,
    created_at: e.created_at,
  };
}

async function serializeLines(db: Kysely<Database>, entryId: string) {
  const lines = await db
    .selectFrom('journal_lines')
    .innerJoin('accounts', 'accounts.account_id', 'journal_lines.account_id')
    .where('journal_lines.entry_id', '=', entryId)
    .select([
      'journal_lines.line_id as line_id',
      'accounts.account_id as account_id',
      'accounts.code as account_code',
      'accounts.name as account_name',
      'journal_lines.side as side',
      'journal_lines.amount as amount',
      'journal_lines.description as description',
    ])
    .execute();
  return lines;
}

export function journalsRouter(db: Kysely<Database>): Router {
  const entries = Router();
  entries.use(requireAuth);

  entries.get('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    let query = db.selectFrom('journal_entries').selectAll().where('company_id', '=', companyId);
    const entryStatus = req.query.status as string | undefined;
    if (entryStatus) query = query.where('status', '=', entryStatus.toUpperCase() as any);
    const rows = await query.orderBy('date', 'desc').execute();
    res.json(rows.map(serializeEntry));
  });

  entries.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db
      .selectFrom('journal_entries')
      .selectAll()
      .where('company_id', '=', companyId ?? '')
      .orderBy('date', 'desc')
      .execute();
    const headers = ['Reference', 'Date', 'Description', 'Debit (N)', 'Credit (N)', 'Status'];
    const dataRows = rows.map((e) => [e.reference, e.date, e.description, e.total_debit, e.total_credit, e.status]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'journal-entries', 'Journal Entries', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'journal-entries', 'Journal Entries', headers, dataRows);
  });

  entries.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const entry = await db
      .selectFrom('journal_entries')
      .selectAll()
      .where('entry_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!entry) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json({ ...serializeEntry(entry), lines: await serializeLines(db, entry.entry_id) });
  });

  entries.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    const lines = body.lines ?? [];
    if (!body.date || !body.description) {
      res.status(400).json({ detail: 'date and description are required.' });
      return;
    }
    if (lines.length < 2) {
      res.status(400).json({ lines: 'A journal entry requires at least 2 lines.' });
      return;
    }
    const totalDebit = lines.filter((l: any) => l.side === 'DEBIT').reduce((s: number, l: any) => s + l.amount, 0);
    const totalCredit = lines.filter((l: any) => l.side === 'CREDIT').reduce((s: number, l: any) => s + l.amount, 0);
    if (Math.round(totalDebit * 100) !== Math.round(totalCredit * 100)) {
      res.status(400).json({ lines: `Debits (${totalDebit.toFixed(2)}) must equal credits (${totalCredit.toFixed(2)}).` });
      return;
    }
    let reference = body.reference;
    if (reference) {
      const dup = await db.selectFrom('journal_entries').select('entry_id').where('reference', '=', reference).where('company_id', '=', companyId).executeTakeFirst();
      if (dup) {
        res.status(400).json({ reference: ['A journal entry with this reference already exists.'] });
        return;
      }
    } else {
      reference = await generateJournalEntryReference(db, companyId);
    }
    const entryId = crypto.randomUUID();
    const now = new Date().toISOString();
    await db
      .insertInto('journal_entries')
      .values({
        entry_id: entryId,
        company_id: companyId,
        reference,
        date: body.date,
        description: body.description,
        status: 'DRAFT',
        entry_type: body.entry_type ?? 'MANUAL',
        total_debit: totalDebit,
        total_credit: totalCredit,
        period_id: null,
        created_by: req.auth!.username,
        approved_by: '',
        approved_at: null,
        voided_by: '',
        voided_at: null,
        updated_at: now,
      })
      .execute();
    for (const line of lines) {
      await db
        .insertInto('journal_lines')
        .values({
          line_id: crypto.randomUUID(),
          company_id: companyId,
          entry_id: entryId,
          account_id: line.account_id,
          side: line.side,
          amount: line.amount,
          description: line.description ?? '',
        })
        .execute();
    }
    const entry = await db.selectFrom('journal_entries').selectAll().where('entry_id', '=', entryId).executeTakeFirstOrThrow();
    res.status(201).json({ ...serializeEntry(entry), lines: await serializeLines(db, entryId) });
  });

  entries.patch('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const entry = await db
      .selectFrom('journal_entries')
      .selectAll()
      .where('entry_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!entry) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (entry.status !== 'DRAFT') {
      res.status(400).json({ detail: 'Only DRAFT entries can be edited.' });
      return;
    }
    const isOwner = entry.created_by === req.auth!.username;
    if (!isOwner && !(await userHasAnyGroup(db, req.auth!.user_id, ['Manager', 'Admin']))) {
      res.status(403).json({ detail: 'Forbidden.' });
      return;
    }
    const body = req.body ?? {};
    const patch: any = { updated_at: new Date().toISOString() };
    if (body.date) patch.date = body.date;
    if (body.description) patch.description = body.description;
    if (body.entry_type) patch.entry_type = body.entry_type;

    if (body.lines) {
      const totalDebit = body.lines.filter((l: any) => l.side === 'DEBIT').reduce((s: number, l: any) => s + l.amount, 0);
      const totalCredit = body.lines.filter((l: any) => l.side === 'CREDIT').reduce((s: number, l: any) => s + l.amount, 0);
      if (Math.round(totalDebit * 100) !== Math.round(totalCredit * 100)) {
        res.status(400).json({ lines: `Debits (${totalDebit.toFixed(2)}) must equal credits (${totalCredit.toFixed(2)}).` });
        return;
      }
      await db.deleteFrom('journal_lines').where('entry_id', '=', entry.entry_id).execute();
      for (const line of body.lines) {
        await db
          .insertInto('journal_lines')
          .values({
            line_id: crypto.randomUUID(),
            company_id: companyId!,
            entry_id: entry.entry_id,
            account_id: line.account_id,
            side: line.side,
            amount: line.amount,
            description: line.description ?? '',
          })
          .execute();
      }
      patch.total_debit = totalDebit;
      patch.total_credit = totalCredit;
    }
    await db.updateTable('journal_entries').set(patch).where('entry_id', '=', entry.entry_id).execute();
    const updated = await db.selectFrom('journal_entries').selectAll().where('entry_id', '=', entry.entry_id).executeTakeFirstOrThrow();
    res.json({ ...serializeEntry(updated), lines: await serializeLines(db, entry.entry_id) });
  });

  entries.delete('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const entry = await db
      .selectFrom('journal_entries')
      .selectAll()
      .where('entry_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!entry) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (entry.status !== 'DRAFT') {
      res.status(400).json({ detail: 'Only DRAFT entries can be deleted.' });
      return;
    }
    await db.deleteFrom('journal_lines').where('entry_id', '=', entry.entry_id).execute();
    await db.deleteFrom('journal_entries').where('entry_id', '=', entry.entry_id).execute();
    res.status(204).send();
  });

  entries.post('/:id/post/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    try {
      await postJournalEntry(db, req.params.id, companyId, req.auth!.username);
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
      return;
    }
    const entry = await db.selectFrom('journal_entries').selectAll().where('entry_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(serializeEntry(entry));
  });

  entries.post('/:id/void/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    try {
      await voidJournalEntry(db, req.params.id, companyId, req.auth!.username);
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
      return;
    }
    const entry = await db.selectFrom('journal_entries').selectAll().where('entry_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(serializeEntry(entry));
  });

  const fiscalYears = Router();
  fiscalYears.use(requireAuth);

  fiscalYears.get('/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('fiscal_years').selectAll().where('company_id', '=', companyId ?? '').execute();
    res.json(rows);
  });

  fiscalYears.post('/', requireLegacyGroup(db, ['Admin']), requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (!body.name || !body.start_date || !body.end_date) {
      res.status(400).json({ detail: 'name, start_date, end_date are required.' });
      return;
    }
    const yearId = crypto.randomUUID();
    await db
      .insertInto('fiscal_years')
      .values({ year_id: yearId, company_id: companyId, name: body.name, start_date: body.start_date, end_date: body.end_date, status: 'OPEN' })
      .execute();
    for (let i = 0; i < 12; i++) {
      const periodStart = addMonthsClamped(body.start_date, i);
      const periodEnd = addDays(addMonthsClamped(periodStart, 1), -1);
      await db
        .insertInto('accounting_periods')
        .values({
          period_id: crypto.randomUUID(),
          company_id: companyId,
          fiscal_year_id: yearId,
          name: monthYearLabel(periodStart),
          start_date: periodStart,
          end_date: periodEnd,
          period_number: i + 1,
          status: 'OPEN',
        })
        .execute();
    }
    const year = await db.selectFrom('fiscal_years').selectAll().where('year_id', '=', yearId).executeTakeFirstOrThrow();
    res.status(201).json(year);
  });

  fiscalYears.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const year = await db
      .selectFrom('fiscal_years')
      .selectAll()
      .where('year_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!year) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const periods = await db.selectFrom('accounting_periods').selectAll().where('fiscal_year_id', '=', year.year_id).execute();
    res.json({ ...year, periods });
  });

  const periods = Router();
  periods.use(requireAuth);

  periods.get('/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const fiscalYearId = req.query.fiscal_year_id as string | undefined;
    let query = db.selectFrom('accounting_periods').selectAll().where('company_id', '=', companyId ?? '');
    if (fiscalYearId) query = query.where('fiscal_year_id', '=', fiscalYearId);
    res.json(await query.execute());
  });

  periods.post('/:id/close/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const period = await db
      .selectFrom('accounting_periods')
      .selectAll()
      .where('period_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!period) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    await db.updateTable('accounting_periods').set({ status: 'CLOSED' }).where('period_id', '=', period.period_id).execute();
    res.json({ ...period, status: 'CLOSED' });
  });

  return Router()
    .use('/entries', entries)
    .use('/fiscal-years', fiscalYears)
    .use('/periods', periods);
}
