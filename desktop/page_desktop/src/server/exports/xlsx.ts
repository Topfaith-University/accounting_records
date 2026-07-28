import ExcelJS from 'exceljs';
import { Response } from 'express';

/** Writes a merged company-name row and report-title row above the data,
 * matching the backend XLSX export header shape. */
function writeCompanyHeader(ws: ExcelJS.Worksheet, companyName: string | null | undefined, title: string, numCols: number): void {
  const lastCol = Math.max(numCols, 1);
  const nameRow = ws.addRow([companyName ?? '']);
  ws.mergeCells(1, 1, 1, lastCol);
  nameRow.font = { bold: true, size: 14 };
  const titleRow = ws.addRow([title]);
  ws.mergeCells(2, 1, 2, lastCol);
  titleRow.font = { bold: true, size: 11 };
  ws.addRow([]);
}

/** Mirrors the live app's openpyxl exports: a bolded header row, one sheet,
 * attachment download (PRD §8/CLAUDE.md's "same bolded-header-row output shape"). */
export async function sendXlsx(
  res: Response,
  filename: string,
  sheetName: string,
  headers: string[],
  rows: (string | number | null)[][],
  companyName: string | null = null,
): Promise<void> {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet(sheetName);
  writeCompanyHeader(ws, companyName, sheetName, headers.length);
  const headerRow = ws.addRow(headers);
  headerRow.font = { bold: true };
  for (const row of rows) ws.addRow(row);
  ws.columns.forEach((col) => {
    col.width = 18;
  });
  const buffer = await wb.xlsx.writeBuffer();
  res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}.xlsx"`);
  res.send(Buffer.from(buffer));
}
