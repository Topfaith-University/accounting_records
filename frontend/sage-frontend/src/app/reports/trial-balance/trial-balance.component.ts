import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ReportsService } from '../../services/reports.service';

@Component({
  selector: 'app-trial-balance',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './trial-balance.component.html',
})
export class TrialBalanceComponent {
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
      this.data = await this.reports.getTrialBalance(this.dateFrom, this.dateTo);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Failed to load report.';
    } finally {
      this.loading = false;
    }
  }

  exportPdf() {
    window.open(this.reports.exportUrl('trial-balance', { date_from: this.dateFrom, date_to: this.dateTo }, 'pdf'));
  }

  exportXlsx() {
    window.open(this.reports.exportUrl('trial-balance', { date_from: this.dateFrom, date_to: this.dateTo }, 'xlsx'));
  }

  get grandTotalDebits(): number {
    return this.data?.total_debits ?? 0;
  }

  get grandTotalCredits(): number {
    return this.data?.total_credits ?? 0;
  }

  get groupedRows(): { type: string; rows: any[] }[] {
    if (!this.data?.rows) return [];
    const groups: { type: string; rows: any[] }[] = [];
    for (const row of this.data.rows) {
      const last = groups[groups.length - 1];
      if (!last || last.type !== row.account_type) {
        groups.push({ type: row.account_type, rows: [row] });
      } else {
        last.rows.push(row);
      }
    }
    return groups;
  }
}
