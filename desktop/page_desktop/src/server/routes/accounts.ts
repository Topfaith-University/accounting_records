import crypto from 'crypto';
import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { requireActiveCompany, requireLegacyGroup } from '../middleware/legacyRbac';
import { getActiveCompanyId } from '../lib/rbac';
import { ACCOUNT_TYPES } from '../lib/accountTypes';
import { computeAccountBalance, generateAccountCode } from '../services/accounts.service';
import { postOpeningBalanceEntry } from '../services/journalPosting.service';
import { sendXlsx } from '../exports/xlsx';
import { sendTablePdf } from '../exports/pdf';

async function serializeAccount(db: Kysely<Database>, account: any) {
  return {
    account_id: account.account_id,
    code: account.code,
    name: account.name,
    account_type: account.account_type,
    normal_balance: account.normal_balance,
    description: account.description,
    opening_balance: account.opening_balance,
    is_active: !!account.is_active,
    is_system: !!account.is_system,
    balance: await computeAccountBalance(db, account.account_id),
    created_at: account.created_at,
    updated_at: account.updated_at,
  };
}

export function accountsRouter(db: Kysely<Database>): Router {
  const router = Router();
  router.use(requireAuth);
  const requireCreateOrEdit = requireLegacyGroup(db, ['Admin', 'Manager']);
  const requireDelete = requireLegacyGroup(db, ['Admin']);

  router.get('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    let query = db.selectFrom('accounts').selectAll().where('company_id', '=', companyId).where('is_active', '=', 1);
    const accountType = req.query.account_type as string | undefined;
    if (accountType) query = query.where('account_type', '=', accountType);
    const rows = await query.execute();
    res.json(await Promise.all(rows.map((r) => serializeAccount(db, r))));
  });

  router.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('accounts').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('code').execute();
    const headers = ['Code', 'Name', 'Type', 'Normal Balance', 'Balance (N)'];
    const dataRows = await Promise.all(rows.map(async (a) => [a.code, a.name, a.account_type, a.normal_balance, await computeAccountBalance(db, a.account_id)]));
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'accounts', 'Chart of Accounts', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'accounts', 'Accounts', headers, dataRows);
  });

  router.get('/types/', (_req, res) => {
    res.json({ account_types: ACCOUNT_TYPES });
  });

  router.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const account = await db
      .selectFrom('accounts')
      .selectAll()
      .where('account_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!account) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeAccount(db, account));
  });

  router.get('/:id/balance/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const account = await db
      .selectFrom('accounts')
      .select('account_id')
      .where('account_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!account) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const asOfDate = req.query.date as string | undefined;
    const balance = await computeAccountBalance(db, req.params.id, asOfDate);
    res.json({ account_id: req.params.id, balance });
  });

  router.get('/:id/ledger/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const account = await db
      .selectFrom('accounts')
      .select('account_id')
      .where('account_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!account) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const rows = await db
      .selectFrom('journal_entries')
      .innerJoin('journal_lines', 'journal_lines.entry_id', 'journal_entries.entry_id')
      .where('journal_entries.company_id', '=', companyId!)
      .where('journal_lines.account_id', '=', req.params.id)
      .where('journal_entries.status', '=', 'POSTED')
      .select([
        'journal_entries.entry_id as entry_id',
        'journal_entries.reference as reference',
        'journal_entries.date as date',
        'journal_entries.description as entry_description',
        'journal_lines.side as side',
        'journal_lines.amount as amount',
        'journal_lines.description as line_description',
        'journal_entries.entry_type as entry_type',
      ])
      .orderBy('journal_entries.date', 'desc')
      .execute();
    res.json({ account_id: req.params.id, entries: rows });
  });

  router.post('/', requireCreateOrEdit, requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (!body.name) {
      res.status(400).json({ name: ['This field is required.'] });
      return;
    }
    if (!ACCOUNT_TYPES.includes(body.account_type)) {
      res.status(400).json({ account_type: ['Not a valid choice.'] });
      return;
    }
    if (!['DEBIT', 'CREDIT'].includes(body.normal_balance)) {
      res.status(400).json({ normal_balance: ['Not a valid choice.'] });
      return;
    }
    let code = body.code;
    if (code) {
      const dup = await db
        .selectFrom('accounts')
        .select('account_id')
        .where('code', '=', code)
        .where('company_id', '=', companyId)
        .executeTakeFirst();
      if (dup) {
        res.status(400).json({ code: ['An account with this code already exists.'] });
        return;
      }
    } else {
      code = await generateAccountCode(db, body.account_type, companyId);
    }

    const accountId = crypto.randomUUID();
    const now = new Date().toISOString();
    const openingBalance = body.opening_balance ?? 0;
    await db
      .insertInto('accounts')
      .values({
        account_id: accountId,
        company_id: companyId,
        code,
        name: body.name,
        account_type: body.account_type,
        normal_balance: body.normal_balance,
        description: body.description ?? '',
        opening_balance: openingBalance,
        is_active: body.is_active === false ? 0 : 1,
        is_system: 0,
        parent_id: body.parent_id ?? null,
        updated_at: now,
      })
      .execute();

    if (openingBalance) {
      await postOpeningBalanceEntry(
        db,
        { account_id: accountId, company_id: companyId, normal_balance: body.normal_balance, name: body.name },
        openingBalance,
        new Date().toISOString().slice(0, 10),
        req.auth!.username,
      );
    }

    const account = await db.selectFrom('accounts').selectAll().where('account_id', '=', accountId).executeTakeFirstOrThrow();
    res.status(201).json(await serializeAccount(db, account));
  });

  router.patch('/:id/', requireCreateOrEdit, async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const account = await db
      .selectFrom('accounts')
      .selectAll()
      .where('account_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!account) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const body = { ...(req.body ?? {}) };
    delete body.parent_id;
    delete body.code;
    delete body.opening_balance;
    delete body.account_id;
    delete body.is_system;
    delete body.balance;
    delete body.created_at;
    if ('is_active' in body) body.is_active = body.is_active ? 1 : 0;
    await db
      .updateTable('accounts')
      .set({ ...body, updated_at: new Date().toISOString() })
      .where('account_id', '=', req.params.id)
      .execute();
    const updated = await db.selectFrom('accounts').selectAll().where('account_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeAccount(db, updated));
  });

  router.delete('/:id/', requireDelete, async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const account = await db
      .selectFrom('accounts')
      .selectAll()
      .where('account_id', '=', req.params.id)
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!account) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (account.is_system) {
      res.status(400).json({ detail: 'System accounts cannot be deleted.' });
      return;
    }
    await db.updateTable('accounts').set({ is_active: 0 }).where('account_id', '=', req.params.id).execute();
    res.status(204).send();
  });

  return router;
}
