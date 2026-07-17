import PdfPrinter from 'pdfmake/src/printer';
import { Response } from 'express';

const FONTS = {
  Helvetica: { normal: 'Helvetica', bold: 'Helvetica-Bold', italics: 'Helvetica-Oblique', bolditalics: 'Helvetica-BoldOblique' },
};

/** Renders a pdfmake document definition to a buffer and streams it inline —
 * mirrors the live app's weasyprint pdf_response() (PRD §4.16/§8): inline
 * Content-Disposition, same intent (view in-browser, not force-download). */
export function sendPdf(res: Response, filename: string, docDefinition: any): void {
  const printer = new PdfPrinter(FONTS);
  const doc = printer.createPdfKitDocument({ defaultStyle: { font: 'Helvetica', fontSize: 9 }, pageMargins: [30, 30, 30, 30], ...docDefinition });
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
export function sendTablePdf(res: Response, filename: string, title: string, headers: string[], rows: (string | number | null)[][]): void {
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
  });
}
