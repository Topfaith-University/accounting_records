import PdfPrinter from 'pdfmake/src/printer';
import { Response } from 'express';

const FONTS = {
  Helvetica: { normal: 'Helvetica', bold: 'Helvetica-Bold', italics: 'Helvetica-Oblique', bolditalics: 'Helvetica-BoldOblique' },
};

/** Letterhead content prepended to every export. pdfmake has no other font
 * registered, so brand consistency comes from color, weight, and spacing. */
function letterheadContent(companyName: string | null | undefined): any[] {
  if (!companyName) return [];
  return [
    { text: companyName, style: 'letterhead' },
    { canvas: [{ type: 'line', x1: 0, y1: 0, x2: 535, y2: 0, lineWidth: 1, lineColor: '#1a1a2e' }], margin: [0, 2, 0, 10] },
  ];
}

/** Renders a pdfmake document definition to a buffer and streams it inline —
 * mirrors the live app's weasyprint pdf_response() (PRD §4.16/§8): inline
 * Content-Disposition, same intent (view in-browser, not force-download). */
export function sendPdf(res: Response, filename: string, docDefinition: any, companyName: string | null = null): void {
  const printer = new PdfPrinter(FONTS);
  const doc = printer.createPdfKitDocument({
    defaultStyle: { font: 'Helvetica', fontSize: 9 },
    pageMargins: [30, 30, 30, 30],
    ...docDefinition,
    content: [...letterheadContent(companyName), ...docDefinition.content],
    styles: { letterhead: { fontSize: 16, bold: true, color: '#1a1a2e' }, ...docDefinition.styles },
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

/** Generic bolded-header table PDF for list exports (accounts, vendors,
 * customers, items, invoices, journal entries, budgets, bank accounts). */
export function sendTablePdf(res: Response, filename: string, title: string, headers: string[], rows: (string | number | null)[][], companyName: string | null = null): void {
  sendPdf(res, filename, {
    content: [
      { text: title, style: 'title' },
      {
        table: {
          headerRows: 1,
          widths: headers.map(() => 'auto'),
          body: [headers.map((h) => ({ text: h, bold: true })), ...rows.map((r) => r.map((v) => String(v ?? '')))],
        },
      },
    ],
    styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
  }, companyName);
}
