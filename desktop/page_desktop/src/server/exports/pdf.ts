import PdfPrinter from 'pdfmake/src/printer';
import { Response } from 'express';

const FONTS = {
  Helvetica: { normal: 'Helvetica', bold: 'Helvetica-Bold', italics: 'Helvetica-Oblique', bolditalics: 'Helvetica-BoldOblique' },
};

const PAGE_CONTENT_WIDTH = 535; // A4 (595pt) minus 30pt margins on each side, matches pageMargins below.

/** Shared palette — mirrors the live app's CSS custom properties
 * (--navy-deep, --navy-primary, --purple, --canvas), extended onto paper. */
export const COLORS = {
  ink: '#10002B',
  rule: '#314991',
  accent: '#6F448D',
  wash: '#F0F4FB',
  positive: '#1C7C54',
  negative: '#B42318',
  hairline: '#E2E6F2',
};

const STYLES = {
  letterhead: { fontSize: 13, bold: true, color: COLORS.ink },
  title: { fontSize: 18, bold: true, color: COLORS.ink, margin: [0, 0, 0, 2] as [number, number, number, number] },
  subtitle: { fontSize: 8.5, color: COLORS.rule, margin: [0, 0, 0, 14] as [number, number, number, number] },
  sectionHeader: { bold: true, fontSize: 8, color: COLORS.rule },
  footerText: { fontSize: 7, color: '#6B7A9E' },
};

/** Letterhead prepended to every export — company name plus a short accent
 * rule, mirroring the backend's shared/_pdf_letterhead.html partial. The
 * rule is deliberately short (not full width): it reads as a flourish under
 * the wordmark, distinct from the full-width hairlines used elsewhere. */
function letterheadContent(companyName: string | null | undefined): any[] {
  if (!companyName) return [];
  return [
    { text: companyName, style: 'letterhead' },
    { canvas: [{ type: 'line', x1: 0, y1: 0, x2: 90, y2: 0, lineWidth: 1.5, lineColor: COLORS.accent }], margin: [0, 3, 0, 14] },
  ];
}

/** A page footer identifying the document wherever it ends up loose —
 * company name, document label, and page count, above a hairline rule. */
function buildFooter(companyName: string | null | undefined, label: string | undefined) {
  const left = [companyName, label].filter(Boolean).join(' · ');
  return (currentPage: number, pageCount: number) => ({
    stack: [
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: PAGE_CONTENT_WIDTH, y2: 0, lineWidth: 0.5, lineColor: COLORS.hairline }] },
      {
        columns: [
          { text: left, style: 'footerText' },
          { text: `Page ${currentPage} of ${pageCount}`, style: 'footerText', alignment: 'right' },
        ],
        margin: [0, 5, 0, 0] as [number, number, number, number],
      },
    ],
    margin: [30, 6, 30, 0] as [number, number, number, number],
  });
}

/** Renders a pdfmake document definition to a buffer and streams it inline —
 * mirrors the live app's weasyprint pdf_response() (PRD §4.16/§8): inline
 * Content-Disposition, same intent (view in-browser, not force-download). */
export function sendPdf(res: Response, filename: string, docDefinition: any, companyName: string | null = null, footerLabel?: string): void {
  const printer = new PdfPrinter(FONTS);
  const doc = printer.createPdfKitDocument({
    defaultStyle: { font: 'Helvetica', fontSize: 9, color: COLORS.ink },
    pageMargins: [30, 30, 30, 40],
    ...docDefinition,
    content: [...letterheadContent(companyName), ...docDefinition.content],
    styles: { ...STYLES, ...docDefinition.styles },
    footer: buildFooter(companyName, footerLabel),
  });
  const chunks: Buffer[] = [];
  doc.on('data', (c: Buffer) => chunks.push(c));
  doc.on('end', () => {
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `inline; filename="${filename}.pdf"`);
    res.send(Buffer.concat(chunks));
  });
  doc.end();
}

/** Title + optional subtitle block, the standard header for every document
 * body (below the letterhead). */
export function titleBlock(title: string, subtitle?: string): any[] {
  return [
    { text: title, style: 'title' },
    ...(subtitle ? [{ text: subtitle, style: 'subtitle' }] : []),
  ];
}

export function today(): string {
  return new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Consistent two-decimal, thousands-separated figure for every table and
 * total across the export system — the same "figures actually line up"
 * discipline a real ledger enforces by hand. */
export function money(n: number | null | undefined): string {
  if (n === null || n === undefined) return '';
  return n.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** A bolded-header table — the shared shape behind every flat list/ledger
 * export (accounts, vendors, customers, items, invoices, journal entries,
 * budgets, bank accounts, statements, GL detail, and the sectioned reports).
 *
 * `zebra` (default on) alternates a faint wash tint per data row — the
 * right read for long flat lists, but turned off for grouped reports
 * (income statement, balance sheet) where section-header shading already
 * carries the grouping and zebra striping would compete with it.
 *
 * `boldRuleBeforeRow` marks one row boundary (counting the header as row 0)
 * as a closing figure: a bold ink rule instead of the ordinary hairline,
 * so it reads as different from every subtotal above it. pdfmake can't draw
 * two literal hairlines at one grid line, so this is the in-table
 * expression of the same "one rule closes a subtotal, two close a total"
 * convention `doubleRule()` renders literally for freestanding totals. */
export function ledgerTable(headers: (string | { text: string; alignment?: string })[], rows: any[][], opts: { widths?: (string | number)[]; zebra?: boolean; boldRuleBeforeRow?: number } = {}): any {
  const zebra = opts.zebra ?? true;
  const body = [
    headers.map((h) => (typeof h === 'string' ? { text: h, bold: true, fontSize: 7.5, color: '#ffffff' } : { bold: true, fontSize: 7.5, color: '#ffffff', ...h })),
    ...rows,
  ];
  return {
    table: {
      headerRows: 1,
      widths: opts.widths ?? headers.map(() => 'auto'),
      body,
    },
    layout: {
      fillColor: (rowIndex: number) => {
        if (rowIndex === 0) return COLORS.rule;
        if (zebra && rowIndex % 2 === 0) return COLORS.wash;
        return null;
      },
      hLineWidth: (rowIndex: number) => (rowIndex === opts.boldRuleBeforeRow ? 1.25 : 0.5),
      vLineWidth: () => 0,
      hLineColor: (rowIndex: number) => (rowIndex === opts.boldRuleBeforeRow ? COLORS.ink : COLORS.hairline),
      paddingTop: () => 5,
      paddingBottom: () => 5,
      paddingLeft: () => 7,
      paddingRight: () => 7,
    },
  };
}

/** The closing-total signature for figures that stand outside a table
 * (statement closing balances, invoice totals): a hairline rule for the
 * running subtotal above it, then a true double rule immediately above the
 * final amount — one line means "add up," two lines mean "this is final,"
 * straight out of how a ledger is closed by hand. */
export function doubleRule(): any {
  return {
    stack: [
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: PAGE_CONTENT_WIDTH, y2: 0, lineWidth: 0.75, lineColor: COLORS.ink }] },
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: PAGE_CONTENT_WIDTH, y2: 0, lineWidth: 0.75, lineColor: COLORS.ink }], margin: [0, 2, 0, 0] as [number, number, number, number] },
    ],
    margin: [0, 6, 0, 6] as [number, number, number, number],
  };
}

/** A right-aligned, fixed-width label/amount row — used to build a compact
 * summary block (Total / Paid / Outstanding, or a single Closing Balance)
 * under a table. Bold by default (a total reads as bold); pass
 * `bold: false` for an informational line like "Paid" sitting between a
 * total and its closing figure. `tone` colors the amount for an
 * outstanding (negative) vs settled (positive) figure. */
export function summaryLine(label: string, value: string, opts: { bold?: boolean; tone?: 'positive' | 'negative' } = {}): any {
  const bold = opts.bold ?? true;
  return {
    columns: [
      { text: '', width: '*' },
      {
        width: 220,
        table: {
          body: [[
            { text: label, bold, fontSize: bold ? 10 : 9, border: [false, false, false, false] },
            { text: value, bold, fontSize: bold ? 10 : 9, alignment: 'right', border: [false, false, false, false], color: opts.tone ? COLORS[opts.tone] : COLORS.ink },
          ]],
        },
        layout: 'noBorders',
      },
    ],
  };
}

/** Generic bolded-header table PDF for list exports (accounts, vendors,
 * customers, items, invoices, journal entries, budgets, bank accounts).
 * Every value every caller passes as a `number` is a currency figure (there
 * are no bare counts in this app's list exports), so a column is treated as
 * money — right-aligned, thousands-separated — the moment any row in it
 * holds a number; text columns stay left-aligned. `subtitle` defaults to a
 * generated-on stamp so every export carries a clear provenance mark even
 * when the caller has nothing more specific to say (a status filter, a
 * date range, etc.). */
export function sendTablePdf(res: Response, filename: string, title: string, headers: string[], rows: (string | number | null)[][], companyName: string | null = null, subtitle?: string): void {
  const numericCols = headers.map((_, col) => rows.some((r) => typeof r[col] === 'number'));
  sendPdf(res, filename, {
    content: [
      ...titleBlock(title, subtitle ?? `Generated ${today()}`),
      ledgerTable(
        headers.map((h, i) => (numericCols[i] ? { text: h, alignment: 'right' } : h)),
        rows.map((r) => r.map((v, i) => ({
          text: typeof v === 'number' ? money(v) : String(v ?? ''),
          fontSize: 9,
          alignment: numericCols[i] ? 'right' : undefined,
        }))),
      ),
    ],
  }, companyName, title);
}
