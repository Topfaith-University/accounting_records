import ExcelJS from 'exceljs';
import { Response } from 'express';

/** Mirrors the live app's openpyxl exports: a bolded header row, one sheet,
 * attachment download (PRD §8/CLAUDE.md's "same bolded-header-row output shape"). */
export async function sendXlsx(
  res: Response,
  filename: string,
  sheetName: string,
  headers: string[],
  rows: (string | number | null)[][],
): Promise<void> {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet(sheetName);
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
