import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ReportsService } from '../../services/reports.service';

@Component({
  selector: 'app-balance-sheet',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './balance-sheet.component.html',
})
export class BalanceSheetComponent {
  asOfDate = '';
  data: any = null;
  loading = false;
  error = '';

  constructor(private reports: ReportsService) {}

  async run() {
    if (!this.asOfDate) return;
    this.loading = true;
    this.error = '';
    this.data = null;
    try {
      this.data = await this.reports.getBalanceSheet(this.asOfDate);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Failed to load report.';
    } finally {
      this.loading = false;
    }
  }

  exportPdf() {
    this.reports.exportFile('balance-sheet', { as_of_date: this.asOfDate }, 'pdf', `balance-sheet-${this.asOfDate}.pdf`);
  }

  exportXlsx() {
    this.reports.exportFile('balance-sheet', { as_of_date: this.asOfDate }, 'xlsx', `balance-sheet-${this.asOfDate}.xlsx`);
  }
}
