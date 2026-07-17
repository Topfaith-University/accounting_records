import crypto from 'crypto';
import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { requireActiveCompany, requireLegacyGroup } from '../middleware/legacyRbac';
import { getActiveCompanyId } from '../lib/rbac';
import { sendXlsx } from '../exports/xlsx';
import { sendTablePdf } from '../exports/pdf';

async function serializeBudgetLine(db: Kysely<Database>, l: any) {
  const account = await db.selectFrom('accounts').select(['code', 'name', 'account_type']).where('account_id', '=', l.account_id).executeTakeFirst();
  return {
    line_id: l.line_id,
    account_code: account?.code ?? null,
    account_name: account?.name ?? null,
    account_type: account?.account_type ?? null,
    budgeted_amount: l.budgeted_amount,
  };
}

async function serializeBudget(db: Kysely<Database>, b: any) {
  const lines = await db.selectFrom('budget_lines').selectAll().where('budget_id', '=', b.budget_id).execute();
  const totalBudgeted = lines.reduce((s, l) => s + l.budgeted_amount, 0);
  return {
    budget_id: b.budget_id,
    name: b.name,
    fiscal_year: b.fiscal_year,
    status: b.status,
    created_by: b.created_by,
    approved_by: b.approved_by,
    approved_at: b.approved_at,
    created_at: b.created_at,
    total_budgeted: totalBudgeted,
  };
}

export function budgetRouter(db: Kysely<Database>): Router {
  const budgets = Router();
  budgets.use(requireAuth);

  budgets.get('/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('budgets').selectAll().where('company_id', '=', companyId ?? '').orderBy('created_at', 'desc').execute();
    res.json(await Promise.all(rows.map((r) => serializeBudget(db, r))));
  });

  budgets.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('budgets').selectAll().where('company_id', '=', companyId ?? '').orderBy('created_at', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (b) => {
        const lines = await db.selectFrom('budget_lines').select('budgeted_amount').where('budget_id', '=', b.budget_id).execute();
        const total = lines.reduce((s, l) => s + l.budgeted_amount, 0);
        return [b.name, b.fiscal_year, total, b.status, b.created_by];
      }),
    );
    const headers = ['Name', 'Fiscal Year', 'Total Budgeted (N)', 'Status', 'Created By'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'budgets', 'Budgets', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'budgets', 'Budgets', headers, dataRows);
  });

  budgets.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const budget = await db.selectFrom('budgets').selectAll().where('budget_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!budget) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const lineRows = await db.selectFrom('budget_lines').selectAll().where('budget_id', '=', budget.budget_id).execute();
    res.json({ ...(await serializeBudget(db, budget)), lines: await Promise.all(lineRows.map((l) => serializeBudgetLine(db, l))) });
  });

  budgets.post('/', requireLegacyGroup(db, ['Admin', 'Manager']), requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    const lines = body.lines ?? [];
    if (!lines.length) {
      res.status(400).json({ lines: 'A budget requires at least one line.' });
      return;
    }
    const accountIds = lines.map((l: any) => l.account_id);
    if (new Set(accountIds).size !== accountIds.length) {
      res.status(400).json({ lines: 'Each account can only appear once per budget.' });
      return;
    }
    if (!body.name || !body.fiscal_year) {
      res.status(400).json({ detail: 'name and fiscal_year are required.' });
      return;
    }
    const budgetId = crypto.randomUUID();
    await db
      .insertInto('budgets')
      .values({ budget_id: budgetId, company_id: companyId, name: body.name, fiscal_year: body.fiscal_year, status: 'DRAFT', created_by: req.auth!.username, approved_by: '', approved_at: null })
      .execute();
    for (const line of lines) {
      await db
        .insertInto('budget_lines')
        .values({ line_id: crypto.randomUUID(), company_id: companyId, budget_id: budgetId, account_id: line.account_id, budgeted_amount: line.budgeted_amount })
        .execute();
    }
    const budget = await db.selectFrom('budgets').selectAll().where('budget_id', '=', budgetId).executeTakeFirstOrThrow();
    const lineRows = await db.selectFrom('budget_lines').selectAll().where('budget_id', '=', budgetId).execute();
    res.status(201).json({ ...(await serializeBudget(db, budget)), lines: await Promise.all(lineRows.map((l) => serializeBudgetLine(db, l))) });
  });

  budgets.delete('/:id/', requireLegacyGroup(db, ['Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const budget = await db.selectFrom('budgets').selectAll().where('budget_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!budget) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (budget.status === 'APPROVED') {
      res.status(400).json({ detail: 'Cannot delete an approved budget.' });
      return;
    }
    await db.deleteFrom('budget_lines').where('budget_id', '=', budget.budget_id).execute();
    await db.deleteFrom('budgets').where('budget_id', '=', budget.budget_id).execute();
    res.status(204).send();
  });

  budgets.post('/:id/approve/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const budget = await db.selectFrom('budgets').selectAll().where('budget_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!budget) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (budget.status === 'APPROVED') {
      res.status(400).json({ detail: 'Already approved.' });
      return;
    }
    await db.updateTable('budgets').set({ status: 'APPROVED', approved_by: req.auth!.username, approved_at: new Date().toISOString() }).where('budget_id', '=', budget.budget_id).execute();
    const updated = await db.selectFrom('budgets').selectAll().where('budget_id', '=', budget.budget_id).executeTakeFirstOrThrow();
    res.json(await serializeBudget(db, updated));
  });

  budgets.get('/:id/variance/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const budget = await db.selectFrom('budgets').selectAll().where('budget_id', '=', req.params.id).where('company_id', '=', companyId).executeTakeFirst();
    if (!budget) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const lineRows = await db
      .selectFrom('budget_lines')
      .innerJoin('accounts', 'accounts.account_id', 'budget_lines.account_id')
      .where('budget_lines.budget_id', '=', budget.budget_id)
      .select(['accounts.account_id as account_id', 'accounts.code as code', 'accounts.name as name', 'accounts.account_type as account_type', 'accounts.normal_balance as normal_balance', 'budget_lines.budgeted_amount as budgeted_amount'])
      .orderBy('accounts.code')
      .execute();

    const lines = [];
    for (const l of lineRows) {
      const postedLines = await db
        .selectFrom('journal_lines')
        .innerJoin('journal_entries', 'journal_entries.entry_id', 'journal_lines.entry_id')
        .where('journal_lines.account_id', '=', l.account_id)
        .where('journal_entries.company_id', '=', companyId)
        .where('journal_entries.status', '=', 'POSTED')
        .select(['journal_lines.side as side', 'journal_lines.amount as amount'])
        .execute();
      const debits = postedLines.filter((p) => p.side === 'DEBIT').reduce((s, p) => s + p.amount, 0);
      const credits = postedLines.filter((p) => p.side === 'CREDIT').reduce((s, p) => s + p.amount, 0);
      const actual = Math.round((l.normal_balance === 'DEBIT' ? debits - credits : credits - debits) * 100) / 100;
      const budgeted = l.budgeted_amount ?? 0;
      const variance = Math.round((budgeted - actual) * 100) / 100;
      lines.push({
        account_id: l.account_id,
        code: l.code,
        name: l.name,
        account_type: l.account_type,
        budgeted,
        actual,
        variance,
        variance_pct: budgeted ? Math.round((variance / budgeted) * 1000) / 10 : null,
      });
    }
    res.json({ budget_id: budget.budget_id, name: budget.name, fiscal_year: budget.fiscal_year, lines });
  });

  return Router().use('/budgets', budgets);
}
