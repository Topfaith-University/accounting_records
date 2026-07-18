import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
import { computeBalanceSheet, computeDashboard, computeGlDetail, computeIncomeStatement, computeTrialBalance } from '../services/reports.service';
import { sendXlsx } from '../exports/xlsx';
import { sendPdf, titleBlock, ledgerTable, money, COLORS } from '../exports/pdf';

function isValidDate(v: string | undefined): v is string {
  return !!v && /^\d{4}-\d{2}-\d{2}$/.test(v);
}

/** A shaded, full-width section marker row (REVENUE, ASSETS, ...) for the
 * grouped reports — carries the same grouping meaning as the backend's
 * .section-header rows, via a cell-level fillColor override rather than
 * the table's own zebra function. */
function sectionRow(label: string, colCount: number): any[] {
  return [
    { text: label, colSpan: colCount, bold: true, fontSize: 7.5, color: COLORS.rule, fillColor: COLORS.wash },
    ...Array(colCount - 1).fill({}),
  ];
}

function subtotalRow(label: string, amount: number, colCount: number): any[] {
  return [
    { text: label, colSpan: colCount - 1, bold: true, fontSize: 9 },
    ...Array(colCount - 2).fill({}),
    { text: money(amount), bold: true, fontSize: 9, alignment: 'right' },
  ];
}

export function reportsRouter(db: Kysely<Database>): Router {
  const router = Router();
  router.use(requireAuth);

  router.get('/trial-balance/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
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
      const dataRows = netted.map((r) => [
        { text: r.code, fontSize: 9 },
        { text: r.name, fontSize: 9 },
        { text: r.account_type, fontSize: 9 },
        { text: r.display_debit ? money(r.display_debit) : '', fontSize: 9, alignment: 'right' },
        { text: r.display_credit ? money(r.display_credit) : '', fontSize: 9, alignment: 'right' },
      ]);
      const totalsRow = [
        { text: 'TOTALS', colSpan: 3, bold: true, fontSize: 9 }, {}, {},
        { text: money(totalD), bold: true, fontSize: 9.5, alignment: 'right' },
        { text: money(totalC), bold: true, fontSize: 9.5, alignment: 'right' },
      ];
      sendPdf(res, `trial-balance-${dateFrom}-${dateTo}`, {
        content: [
          ...titleBlock('Trial Balance', `${dateFrom} to ${dateTo}`),
          ledgerTable(
            ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'],
            [...dataRows, totalsRow],
            { widths: ['auto', '*', 'auto', 'auto', 'auto'], boldRuleBeforeRow: dataRows.length + 1 },
          ),
        ],
      }, companyName, 'Trial Balance');
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'];
      const dataRows: any[][] = netted.map((r) => [r.code, r.name, r.account_type, r.display_debit || null, r.display_credit || null]);
      dataRows.push(['', 'TOTALS', '', totalD, totalC]);
      await sendXlsx(res, `trial-balance-${dateFrom}-${dateTo}`, 'Trial Balance', headers, dataRows, companyName);
      return;
    }
    res.json({ rows, date_from: dateFrom, date_to: dateTo, total_debits: Math.round(rows.reduce((s, r) => s + r.total_debits, 0) * 100) / 100, total_credits: Math.round(rows.reduce((s, r) => s + r.total_credits, 0) * 100) / 100 });
  });

  router.get('/income-statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
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
      const line = (r: any) => [{ text: r.name, fontSize: 9 }, { text: r.account_type, fontSize: 9 }, { text: money(r.balance), fontSize: 9, alignment: 'right' }];
      const body = [
        sectionRow('REVENUE', 3),
        ...data.revenue.map(line),
        subtotalRow('Total Revenue', data.total_revenue, 3),
        sectionRow('COST OF SALES', 3),
        ...data.cost_of_sales.map(line),
        subtotalRow('Gross Profit', data.gross_profit, 3),
        sectionRow('EXPENSES', 3),
        ...data.expenses.map(line),
        subtotalRow('Total Expenses', data.total_expenses, 3),
        [
          { text: 'Net Surplus / (Deficit)', colSpan: 2, bold: true, fontSize: 10, color: data.net_surplus >= 0 ? COLORS.positive : COLORS.negative },
          {},
          { text: money(data.net_surplus), bold: true, fontSize: 10, alignment: 'right', color: data.net_surplus >= 0 ? COLORS.positive : COLORS.negative },
        ],
      ];
      sendPdf(res, `income-statement-${dateFrom}-${dateTo}`, {
        content: [
          ...titleBlock('Income Statement', `${dateFrom} to ${dateTo}`),
          ledgerTable(['Account', 'Type', 'Amount (N)'], body, { widths: ['*', 'auto', 'auto'], zebra: false, boldRuleBeforeRow: body.length }),
        ],
      }, companyName, 'Income Statement');
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
      await sendXlsx(res, `income-statement-${dateFrom}-${dateTo}`, 'Income Statement', headers, rows, companyName);
      return;
    }
    res.json(data);
  });

  router.get('/balance-sheet/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
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
      const line = (r: any) => [{ text: r.name, fontSize: 9 }, { text: r.account_type, fontSize: 9 }, { text: money(r.balance), fontSize: 9, alignment: 'right' }];
      const body: any[] = [];
      for (const [label, items, total] of [
        ['Assets', data.assets, data.total_assets],
        ['Liabilities', data.liabilities, data.total_liabilities],
        ['Equity', data.equity, data.total_equity],
      ] as const) {
        body.push(sectionRow((label as string).toUpperCase(), 3));
        body.push(...(items as any[]).map(line));
        body.push(subtotalRow(`Total ${label}`, total as number, 3));
      }
      const lastRow = body[body.length - 1];
      lastRow[0] = { ...lastRow[0], color: data.is_balanced ? COLORS.positive : COLORS.negative };
      lastRow[2] = { ...lastRow[2], color: data.is_balanced ? COLORS.positive : COLORS.negative };
      sendPdf(res, `balance-sheet-${asOfDate}`, {
        content: [
          ...titleBlock('Balance Sheet', `As of ${asOfDate}`),
          ledgerTable(['Account', 'Type', 'Balance (N)'], body, { widths: ['*', 'auto', 'auto'], zebra: false, boldRuleBeforeRow: body.length }),
          {
            text: data.is_balanced ? 'Assets = Liabilities + Equity (balanced)' : 'Warning: balance sheet does not balance',
            fontSize: 8, bold: true, color: data.is_balanced ? COLORS.positive : COLORS.negative, margin: [0, 8, 0, 0],
          },
        ],
      }, companyName, 'Balance Sheet');
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
      await sendXlsx(res, `balance-sheet-${asOfDate}`, 'Balance Sheet', headers, rows, companyName);
      return;
    }
    res.json(data);
  });

  router.get('/gl-detail/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
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
      const dataRows = data.lines.map((l) => [
        { text: l.date, fontSize: 9 },
        { text: l.reference, fontSize: 9 },
        { text: l.entry_description, fontSize: 9 },
        { text: l.entry_type || 'MANUAL', fontSize: 9 },
        { text: l.side, fontSize: 9, color: l.side === 'DEBIT' ? '#1a73e8' : COLORS.positive },
        { text: money(l.amount), fontSize: 9, alignment: 'right' },
        { text: money(l.running_balance), fontSize: 9, alignment: 'right' },
      ]);
      const totalsRow = [
        { text: 'CLOSING BALANCE', colSpan: 6, bold: true, fontSize: 9 }, {}, {}, {}, {}, {},
        { text: money(data.closing_balance), bold: true, fontSize: 9.5, alignment: 'right' },
      ];
      sendPdf(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, {
        content: [
          ...titleBlock(`GL Detail — ${data.account_code} ${data.account_name}`, `${dateFrom} to ${dateTo}`),
          ledgerTable(
            ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'],
            [...dataRows, totalsRow],
            { widths: ['auto', 'auto', '*', 'auto', 'auto', 'auto', 'auto'], boldRuleBeforeRow: dataRows.length + 1 },
          ),
        ],
      }, companyName, `GL Detail — ${data.account_code}`);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'];
      const rows: any[][] = data.lines.map((l) => [l.date, l.reference, l.entry_description, l.entry_type || 'MANUAL', l.side, l.amount, l.running_balance]);
      rows.push(['', '', '', '', 'CLOSING BALANCE', '', data.closing_balance]);
      await sendXlsx(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, `GL ${data.account_code}`, headers, rows, companyName);
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
