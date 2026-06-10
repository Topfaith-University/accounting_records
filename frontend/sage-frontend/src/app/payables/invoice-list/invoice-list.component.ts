import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { PayablesService } from '../../services/payables.service';

@Component({
  selector: 'app-invoice-list',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './invoice-list.component.html',
})
export class InvoiceListComponent implements OnInit {
  invoices: any[] = [];
  loading = true;
  error = '';
  activeTab: 'ALL' | 'DRAFT' | 'POSTED' | 'PAID' | 'VOID' = 'ALL';

  constructor(private payables: PayablesService) {}

  async ngOnInit() { await this.load(); }

  async load() {
    this.loading = true;
    try {
      const params = this.activeTab !== 'ALL' ? { status: this.activeTab } : {};
      const data = await this.payables.getInvoices(params);
      this.invoices = data.results ?? data;
    } catch { this.error = 'Failed to load invoices.'; }
    finally { this.loading = false; }
  }

  async setTab(tab: string) {
    this.activeTab = tab as typeof this.activeTab;
    await this.load();
  }

  statusColor(s: string) {
    return { DRAFT: '#f59e0b', POSTED: '#1a73e8', PAID: '#10b981', VOID: '#ef4444' }[s] ?? '#888';
  }

  statusBadgeStyle(status: string): Record<string, string> {
    const map: Record<string, Record<string, string>> = {
      DRAFT:  { background: '#F3F4F6', color: '#6B7280' },
      POSTED: { background: '#EFF6FF', color: '#1D4ED8' },
      PAID:   { background: '#F0FDF4', color: '#15803D' },
      VOID:   { background: '#FFF1F2', color: '#B91C1C' },
    };
    return {
      ...(map[status] ?? map['DRAFT']),
      display: 'inline-block', padding: '.15rem .5rem',
      borderRadius: '4px', fontSize: '.75rem', fontWeight: '700',
      textTransform: 'uppercase', letterSpacing: '.04em',
    };
  }
}
