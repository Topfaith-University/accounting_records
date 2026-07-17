import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { getActiveCompanyId } from '../lib/rbac';
import { computeBalanceSheet, computeDashboard, computeGlDetail, computeIncomeStatement, computeTrialBalance } from '../services/reports.service';
import { sendXlsx } from '../exports/xlsx';
import { sendPdf } from '../exports/pdf';

function isValidDate(v: string | undefined): v is string {
  return !!v && /^\d{4}-\d{2}-\d{2}$/.test(v);
}

const bold = (h: string) => ({ text: h, bold: true });

export function reportsRouter(db: Kysely<Database>): Router {
  const router = Router();
  router.use(requireAuth);

  router.get('/trial-balance/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
    const dateFrom = req.query.date_from as string | undefined;
    const dateTo = req.query.date_to as string | undefined;
    if (!dateFrom || !dateTo) {
      res.status(400).json({ detail: 'date_from and date_to are required.' });
      return;
    }
    if (!isValidDate(dateFrom) || !isValidDate(dateTo)) {
      res.status(400).json({ detail: 'Invalid date format. Use YYYY-MM-DD.' });
      return;
    }
    const rows = await computeTrialBalance(db, companyId, dateFrom, dateTo);
    const fmt = (req.query.format as string) || 'json';

    // Netting rule (PRD §4.15): each row shows only its net debit OR net credit,
    // never both — mirrors trial_balance view's display_debit/display_credit.
    const netted = rows.map((r) => ({
      ...r,
      display_debit: Math.max(0, Math.round((r.total_debits - r.total_credits) * 100) / 100),
      display_credit: Math.max(0, Math.round((r.total_credits - r.total_debits) * 100) / 100),
    }));
    const totalD = Math.round(netted.reduce((s, r) => s + r.display_debit, 0) * 100) / 100;
    const totalC = Math.round(netted.reduce((s, r) => s + r.display_credit, 0) * 100) / 100;

    if (fmt === 'pdf') {
      sendPdf(res, `trial-balance-${dateFrom}-${dateTo}`, {
        content: [
          { text: `Trial Balance (${dateFrom} to ${dateTo})`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', '*', 'auto', 'auto', 'auto'],
              body: [
                ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'].map(bold),
                ...netted.map((r) => [r.code, r.name, r.account_type, r.display_debit || '', r.display_credit || '']),
                [{ text: '', colSpan: 3 }, {}, {}, bold(String(totalD)), bold(String(totalC))],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'];
      const dataRows: any[][] = netted.map((r) => [r.code, r.name, r.account_type, r.display_debit || null, r.display_credit || null]);
      dataRows.push(['', 'TOTALS', '', totalD, totalC]);
      await sendXlsx(res, `trial-balance-${dateFrom}-${dateTo}`, 'Trial Balance', headers, dataRows);
      return;
    }
    res.json({ rows, date_from: dateFrom, date_to: dateTo, total_debits: Math.round(rows.reduce((s, r) => s + r.total_debits, 0) * 100) / 100, total_credits: Math.round(rows.reduce((s, r) => s + r.total_credits, 0) * 100) / 100 });
  });

  router.get('/income-statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
    const dateFrom = req.query.date_from as string | undefined;
    const dateTo = req.query.date_to as string | undefined;
    if (!dateFrom || !dateTo) {
      res.status(400).json({ detail: 'date_from and date_to are required.' });
      return;
    }
    if (!isValidDate(dateFrom) || !isValidDate(dateTo)) {
      res.status(400).json({ detail: 'Invalid date format. Use YYYY-MM-DD.' });
      return;
    }
    const data = await computeIncomeStatement(db, companyId, dateFrom, dateTo);
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `income-statement-${dateFrom}-${dateTo}`, {
        content: [
          { text: `Income Statement (${dateFrom} to ${dateTo})`, style: 'title' },
          { text: 'REVENUE', style: 'section' },
          ...data.revenue.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Total Revenue: ₦${data.total_revenue.toLocaleString()}`, bold: true },
          { text: 'COST OF SALES', style: 'section' },
          ...data.cost_of_sales.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Gross Profit: ₦${data.gross_profit.toLocaleString()}`, bold: true },
          { text: 'EXPENSES', style: 'section' },
          ...data.expenses.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Total Expenses: ₦${data.total_expenses.toLocaleString()}`, bold: true },
          { text: `Net Surplus / (Deficit): ₦${data.net_surplus.toLocaleString()}`, bold: true, margin: [0, 10, 0, 0] },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] }, section: { bold: true, margin: [0, 8, 0, 4] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Account', 'Type', 'Amount (N)'];
      const rows: any[][] = [
        ['REVENUE', '', ''],
        ...data.revenue.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Total Revenue', '', data.total_revenue],
        ['COST OF SALES', '', ''],
        ...data.cost_of_sales.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Gross Profit', '', data.gross_profit],
        ['EXPENSES', '', ''],
        ...data.expenses.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Total Expenses', '', data.total_expenses],
        ['Net Surplus / (Deficit)', '', data.net_surplus],
      ];
      await sendXlsx(res, `income-statement-${dateFrom}-${dateTo}`, 'Income Statement', headers, rows);
      return;
    }
    res.json(data);
  });

  router.get('/balance-sheet/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
    const asOfDate = req.query.as_of_date as string | undefined;
    if (!asOfDate) {
      res.status(400).json({ detail: 'as_of_date is required.' });
      return;
    }
    if (!isValidDate(asOfDate)) {
      res.status(400).json({ detail: 'Invalid date format. Use YYYY-MM-DD.' });
      return;
    }
    const data = await computeBalanceSheet(db, companyId, asOfDate);
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      const section = (label: string, items: any[], total: number) => [
        { text: label, style: 'section' },
        ...items.map((r) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
        { text: `Total ${label}: ₦${total.toLocaleString()}`, bold: true },
      ];
      sendPdf(res, `balance-sheet-${asOfDate}`, {
        content: [
          { text: `Balance Sheet (as of ${asOfDate})`, style: 'title' },
          ...section('Assets', data.assets, data.total_assets),
          ...section('Liabilities', data.liabilities, data.total_liabilities),
          ...section('Equity', data.equity, data.total_equity),
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] }, section: { bold: true, margin: [0, 8, 0, 4] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Account', 'Type', 'Balance (N)'];
      const rows: any[][] = [];
      for (const [label, items, total] of [
        ['ASSETS', data.assets, data.total_assets],
        ['LIABILITIES', data.liabilities, data.total_liabilities],
        ['EQUITY', data.equity, data.total_equity],
      ] as const) {
        rows.push([label, '', '']);
        for (const r of items as any[]) rows.push([r.name, r.account_type, r.balance]);
        rows.push([`Total ${(label as string).charAt(0) + (label as string).slice(1).toLowerCase()}`, '', total]);
      }
      await sendXlsx(res, `balance-sheet-${asOfDate}`, 'Balance Sheet', headers, rows);
      return;
    }
    res.json(data);
  });

  router.get('/gl-detail/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
    const accountId = req.query.account_id as string | undefined;
    const dateFrom = req.query.date_from as string | undefined;
    const dateTo = req.query.date_to as string | undefined;
    if (!accountId || !dateFrom || !dateTo) {
      res.status(400).json({ detail: 'account_id, date_from, and date_to are required.' });
      return;
    }
    if (!isValidDate(dateFrom) || !isValidDate(dateTo)) {
      res.status(400).json({ detail: 'Invalid date format. Use YYYY-MM-DD.' });
      return;
    }
    const data = await computeGlDetail(db, companyId, accountId, dateFrom, dateTo);
    if (!data) {
      res.status(404).json({ detail: 'Account not found.' });
      return;
    }
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, {
        content: [
          { text: `GL Detail — ${data.account_code} ${data.account_name} (${dateFrom} to ${dateTo})`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', 'auto', '*', 'auto', 'auto', 'auto', 'auto'],
              body: [
                ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'].map(bold),
                ...data.lines.map((l) => [l.date, l.reference, l.entry_description, l.entry_type || 'MANUAL', l.side, l.amount, l.running_balance]),
                [{ text: '', colSpan: 5 }, {}, {}, {}, {}, bold('CLOSING BALANCE'), bold(String(data.closing_balance))],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 13, bold: true, margin: [0, 0, 0, 10] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'];
      const rows: any[][] = data.lines.map((l) => [l.date, l.reference, l.entry_description, l.entry_type || 'MANUAL', l.side, l.amount, l.running_balance]);
      rows.push(['', '', '', '', 'CLOSING BALANCE', '', data.closing_balance]);
      await sendXlsx(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, `GL ${data.account_code}`, headers, rows);
      return;
    }
    res.json(data);
  });

  router.get('/dashboard/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
    res.json(await computeDashboard(db, companyId));
  });

  return router;
}
