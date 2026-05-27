import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ReportsService } from '../../services/reports.service';
import { AccountsService } from '../../services/accounts.service';

@Component({
  selector: 'app-gl-detail',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './gl-detail.component.html',
})
export class GlDetailComponent implements OnInit {
  accounts: any[] = [];
  accountId = '';
  dateFrom = '';
  dateTo = '';
  data: any = null;
  loading = false;
  error = '';

  constructor(private reports: ReportsService, private accountsService: AccountsService) {}

  async ngOnInit() {
    try {
      const result = await this.accountsService.getAll();
      this.accounts = result.results ?? result;
    } catch {
      this.error = 'Could not load accounts list.';
    }
  }

  async run() {
    if (!this.accountId || !this.dateFrom || !this.dateTo) return;
    this.loading = true;
    this.error = '';
    this.data = null;
    try {
      this.data = await this.reports.getGlDetail(this.accountId, this.dateFrom, this.dateTo);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Failed to load report.';
    } finally {
      this.loading = false;
    }
  }

  exportPdf() {
    window.open(this.reports.exportUrl('gl-detail', { account_id: this.accountId, date_from: this.dateFrom, date_to: this.dateTo }, 'pdf'));
  }

  exportXlsx() {
    window.open(this.reports.exportUrl('gl-detail', { account_id: this.accountId, date_from: this.dateFrom, date_to: this.dateTo }, 'xlsx'));
  }

  entryTypeBadgeStyle(type: string): Record<string, string> {
    const styles: Record<string, Record<string, string>> = {
      MANUAL:           { background: '#F3F4F6', color: '#6B7280' },
      BANK_TRANSACTION: { background: '#EFF6FF', color: '#1D4ED8' },
      AP_PAYMENT:       { background: '#FFF7ED', color: '#C2410C' },
      AR_RECEIPT:       { background: '#F0FDF4', color: '#15803D' },
    };
    return {
      ...(styles[type] ?? styles['MANUAL']),
      display: 'inline-block', padding: '.15rem .5rem',
      borderRadius: '4px', fontSize: '.75rem', fontWeight: '700',
      textTransform: 'uppercase', letterSpacing: '.04em',
    };
  }
}
