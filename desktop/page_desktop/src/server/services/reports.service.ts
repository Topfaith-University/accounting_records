import { Kysely } from 'kysely';
import { Database } from '../db/types';

const REVENUE_TYPES = ['Sales', 'Other Incomes'];
const COS_TYPES = ['Cost of Sales'];
const EXPENSE_TYPES = ['Expenses', 'Income Tax'];
const ASSET_TYPES = ['Non-Current Assets', 'Current Assets'];
const LIABILITY_TYPES = ['Current Liabilities', 'Non-Current Liabilities'];
const EQUITY_TYPES = ["Owner's Equity"];

function accountBalance(normalBalance: string, debits: number, credits: number): number {
  const raw = normalBalance === 'DEBIT' ? debits - credits : credits - debits;
  return Math.round(raw * 100) / 100;
}

async function balancesForTypes(db: Kysely<Database>, companyId: string, types: string[], dateFrom: string, dateTo: string) {
  const accounts = await db.selectFrom('accounts').selectAll().where('company_id', '=', companyId).where('is_active', '=', 1).where('account_type', 'in', types).orderBy('code').execute();
  const rows = [];
  for (const a of accounts) {
    const lines = await db
      .selectFrom('journal_lines')
      .innerJoin('journal_entries', 'journal_entries.entry_id', 'journal_lines.entry_id')
      .where('journal_lines.account_id', '=', a.account_id)
      .where('journal_entries.company_id', '=', companyId)
      .where('journal_entries.status', '=', 'POSTED')
      .where('journal_entries.date', '>=', dateFrom)
      .where('journal_entries.date', '<=', dateTo)
      .select(['journal_lines.side as side', 'journal_lines.amount as amount'])
      .execute();
    const debits = lines.filter((l) => l.side === 'DEBIT').reduce((s, l) => s + l.amount, 0);
    const credits = lines.filter((l) => l.side === 'CREDIT').reduce((s, l) => s + l.amount, 0);
    rows.push({
      account_id: a.account_id,
      code: a.code,
      name: a.name,
      account_type: a.account_type,
      normal_balance: a.normal_balance,
      total_debits: Math.round(debits * 100) / 100,
      total_credits: Math.round(credits * 100) / 100,
      balance: accountBalance(a.normal_balance, debits, credits),
    });
  }
  return rows;
}

/** Mirrors reports/services.py's compute_trial_balance exactly. */
export async function computeTrialBalance(db: Kysely<Database>, companyId: string, dateFrom: string, dateTo: string) {
  const allActive = await db.selectFrom('accounts').selectAll().where('company_id', '=', companyId).where('is_active', '=', 1).orderBy('code').execute();
  const rows = [];
  for (const a of allActive) {
    const lines = await db
      .selectFrom('journal_lines')
      .innerJoin('journal_entries', 'journal_entries.entry_id', 'journal_lines.entry_id')
      .where('journal_lines.account_id', '=', a.account_id)
      .where('journal_entries.company_id', '=', companyId)
      .where('journal_entries.status', '=', 'POSTED')
      .where('journal_entries.date', '>=', dateFrom)
      .where('journal_entries.date', '<=', dateTo)
      .select(['journal_lines.side as side', 'journal_lines.amount as amount'])
      .execute();
    const debits = lines.filter((l) => l.side === 'DEBIT').reduce((s, l) => s + l.amount, 0);
    const credits = lines.filter((l) => l.side === 'CREDIT').reduce((s, l) => s + l.amount, 0);
    rows.push({
      account_id: a.account_id,
      code: a.code,
      name: a.name,
      account_type: a.account_type,
      normal_balance: a.normal_balance,
      total_debits: Math.round(debits * 100) / 100,
      total_credits: Math.round(credits * 100) / 100,
      balance: accountBalance(a.normal_balance, debits, credits),
    });
  }
  return rows;
}

/** Mirrors reports/services.py's compute_income_statement exactly. */
export async function computeIncomeStatement(db: Kysely<Database>, companyId: string, dateFrom: string, dateTo: string) {
  const allTypes = [...REVENUE_TYPES, ...COS_TYPES, ...EXPENSE_TYPES];
  const rows = await balancesForTypes(db, companyId, allTypes, dateFrom, dateTo);
  const revenue = rows.filter((r) => REVENUE_TYPES.includes(r.account_type)).map(({ normal_balance, total_debits, total_credits, ...rest }) => rest);
  const cos = rows.filter((r) => COS_TYPES.includes(r.account_type)).map(({ normal_balance, total_debits, total_credits, ...rest }) => rest);
  const expenses = rows.filter((r) => EXPENSE_TYPES.includes(r.account_type)).map(({ normal_balance, total_debits, total_credits, ...rest }) => rest);

  const totalRevenue = revenue.reduce((s, r) => s + r.balance, 0);
  const totalCos = cos.reduce((s, r) => s + r.balance, 0);
  const totalExpenses = expenses.reduce((s, r) => s + r.balance, 0);
  const grossProfit = Math.round((totalRevenue - totalCos) * 100) / 100;
  const netSurplus = Math.round((grossProfit - totalExpenses) * 100) / 100;

  return {
    date_from: dateFrom,
    date_to: dateTo,
    revenue,
    total_revenue: Math.round(totalRevenue * 100) / 100,
    cost_of_sales: cos,
    total_cos: Math.round(totalCos * 100) / 100,
    gross_profit: grossProfit,
    expenses,
    total_expenses: Math.round(totalExpenses * 100) / 100,
    net_surplus: netSurplus,
  };
}

/** Mirrors reports/services.py's compute_balance_sheet exactly, including the
 * synthetic P&L rollup row computed live (PRD §4.15 / no closing-entry mechanism). */
export async function computeBalanceSheet(db: Kysely<Database>, companyId: string, asOfDate: string) {
  const allTypes = [...ASSET_TYPES, ...LIABILITY_TYPES, ...EQUITY_TYPES];
  const rows = await balancesForTypes(db, companyId, allTypes, '0001-01-01', asOfDate);
  const strip = ({ normal_balance, total_debits, total_credits, ...rest }: any) => rest;
  const assets = rows.filter((r) => ASSET_TYPES.includes(r.account_type)).map(strip);
  const liabilities = rows.filter((r) => LIABILITY_TYPES.includes(r.account_type)).map(strip);
  const equity: any[] = rows.filter((r) => EQUITY_TYPES.includes(r.account_type)).map(strip);

  const pl = await computeIncomeStatement(db, companyId, '0001-01-01', asOfDate);
  if (pl.net_surplus !== 0) {
    equity.push({
      account_id: null,
      code: '',
      name: 'Profit/(Loss) — current & prior periods',
      account_type: "Owner's Equity",
      balance: pl.net_surplus,
    });
  }

  const totalAssets = Math.round(assets.reduce((s, r) => s + r.balance, 0) * 100) / 100;
  const totalLiabilities = Math.round(liabilities.reduce((s, r) => s + r.balance, 0) * 100) / 100;
  const totalEquity = Math.round(equity.reduce((s, r) => s + r.balance, 0) * 100) / 100;

  return {
    as_of_date: asOfDate,
    assets,
    total_assets: totalAssets,
    liabilities,
    total_liabilities: totalLiabilities,
    equity,
    total_equity: totalEquity,
    is_balanced: Math.abs(totalAssets - (totalLiabilities + totalEquity)) < 0.01,
  };
}

/** Mirrors reports/services.py's compute_gl_detail exactly. */
export async function computeGlDetail(db: Kysely<Database>, companyId: string, accountId: string, dateFrom: string, dateTo: string) {
  const account = await db.selectFrom('accounts').select(['code', 'name', 'normal_balance']).where('account_id', '=', accountId).where('company_id', '=', companyId).executeTakeFirst();
  if (!account) return null;

  const rows = await db
    .selectFrom('journal_lines')
    .innerJoin('journal_entries', 'journal_entries.entry_id', 'journal_lines.entry_id')
    .where('journal_lines.account_id', '=', accountId)
    .where('journal_entries.company_id', '=', companyId)
    .where('journal_entries.status', '=', 'POSTED')
    .where('journal_entries.date', '>=', dateFrom)
    .where('journal_entries.date', '<=', dateTo)
    .select([
      'journal_lines.line_id as line_id',
      'journal_entries.entry_id as entry_id',
      'journal_entries.reference as reference',
      'journal_entries.date as date',
      'journal_entries.description as entry_description',
      'journal_lines.side as side',
      'journal_lines.amount as amount',
      'journal_lines.description as line_description',
      'journal_entries.entry_type as entry_type',
    ])
    .orderBy('journal_entries.date', 'asc')
    .orderBy('journal_entries.reference', 'asc')
    .execute();

  let runningBalance = 0;
  const lines = rows.map((r) => {
    const amount = r.amount ?? 0;
    if (account.normal_balance === 'DEBIT') {
      runningBalance += r.side === 'DEBIT' ? amount : -amount;
    } else {
      runningBalance += r.side === 'CREDIT' ? amount : -amount;
    }
    return {
      line_id: r.line_id,
      entry_id: r.entry_id,
      reference: r.reference,
      date: r.date,
      entry_description: r.entry_description,
      side: r.side,
      amount: Math.round(amount * 100) / 100,
      line_description: r.line_description,
      entry_type: r.entry_type,
      running_balance: Math.round(runningBalance * 100) / 100,
    };
  });

  return {
    account_id: accountId,
    account_code: account.code,
    account_name: account.name,
    date_from: dateFrom,
    date_to: dateTo,
    lines,
    closing_balance: Math.round(runningBalance * 100) / 100,
  };
}

/** Mirrors reports/views.py's dashboard exactly, including quirk 5 (PARTIAL is
 * a dead status, never filters anything extra — do not "fix"). */
export async function computeDashboard(db: Kysely<Database>, companyId: string) {
  const accounts = await db.selectFrom('accounts').selectAll().where('company_id', '=', companyId).where('is_active', '=', 1).execute();
  const ASSET_T = new Set(['Current Assets', 'Non-Current Assets']);
  const LIAB_T = new Set(['Current Liabilities', 'Non-Current Liabilities']);

  let totalAssets = 0;
  let totalLiabilities = 0;
  for (const a of accounts) {
    const lines = await db
      .selectFrom('journal_lines')
      .innerJoin('journal_entries', 'journal_entries.entry_id', 'journal_lines.entry_id')
      .where('journal_lines.account_id', '=', a.account_id)
      .where('journal_entries.company_id', '=', companyId)
      .where('journal_entries.status', '=', 'POSTED')
      .select(['journal_lines.side as side', 'journal_lines.amount as amount'])
      .execute();
    const debits = lines.filter((l) => l.side === 'DEBIT').reduce((s, l) => s + l.amount, 0);
    const credits = lines.filter((l) => l.side === 'CREDIT').reduce((s, l) => s + l.amount, 0);
    const balance = a.normal_balance === 'DEBIT' ? debits - credits : credits - debits;
    if (ASSET_T.has(a.account_type)) totalAssets += balance;
    else if (LIAB_T.has(a.account_type)) totalLiabilities += balance;
  }

  // 'PARTIAL' is never a real status (PRD §10 quirk 5) — kept in the filter, permanently a no-op, on purpose.
  const AP_STATUSES = ['POSTED', 'PARTIAL'] as unknown as ('DRAFT' | 'POSTED' | 'VOID' | 'PAID')[];
  const apInvoices = await db.selectFrom('purchase_invoices').select(['total_amount', 'amount_paid']).where('company_id', '=', companyId).where('status', 'in', AP_STATUSES).execute();
  const apOutstanding = apInvoices.reduce((s, i) => s + (i.total_amount - i.amount_paid), 0);

  const arInvoices = await db.selectFrom('sales_invoices').select(['total_amount', 'amount_received']).where('company_id', '=', companyId).where('status', 'in', AP_STATUSES).execute();
  const arOutstanding = arInvoices.reduce((s, i) => s + (i.total_amount - i.amount_received), 0);

  const recentEntries = await db
    .selectFrom('journal_entries')
    .select(['entry_id', 'reference', 'date', 'description', 'total_debit'])
    .where('company_id', '=', companyId)
    .where('status', '=', 'POSTED')
    .orderBy('date', 'desc')
    .orderBy('created_at', 'desc')
    .limit(10)
    .execute();

  return {
    total_assets: Math.round(totalAssets * 100) / 100,
    total_liabilities: Math.round(totalLiabilities * 100) / 100,
    net_equity: Math.round((totalAssets - totalLiabilities) * 100) / 100,
    ap_outstanding: Math.round(apOutstanding * 100) / 100,
    ar_outstanding: Math.round(arOutstanding * 100) / 100,
    recent_entries: recentEntries.map((e) => ({ entry_id: e.entry_id, reference: e.reference, date: e.date, description: e.description, total_debit: e.total_debit })),
  };
}
