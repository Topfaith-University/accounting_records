import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ReportsService } from '../../services/reports.service';

@Component({
  selector: 'app-income-statement',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './income-statement.component.html',
})
export class IncomeStatementComponent {
  dateFrom = '';
  dateTo = '';
  data: any = null;
  loading = false;
  error = '';

  constructor(private reports: ReportsService) {}

  async run() {
    if (!this.dateFrom || !this.dateTo) return;
    this.loading = true;
    this.error = '';
    this.data = null;
    try {
      this.data = await this.reports.getIncomeStatement(this.dateFrom, this.dateTo);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Failed to load report.';
    } finally {
      this.loading = false;
    }
  }

  exportPdf() {
    this.reports.exportFile('income-statement', { date_from: this.dateFrom, date_to: this.dateTo }, 'pdf', `income-statement-${this.dateFrom}-${this.dateTo}.pdf`);
  }

  exportXlsx() {
    this.reports.exportFile('income-statement', { date_from: this.dateFrom, date_to: this.dateTo }, 'xlsx', `income-statement-${this.dateFrom}-${this.dateTo}.xlsx`);
  }
}
