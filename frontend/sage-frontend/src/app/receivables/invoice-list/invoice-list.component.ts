import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import axios from 'axios';
import { ReceivablesService } from '../../services/receivables.service';
import { API_ROOT } from '../../services/api-base';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-sales-invoice-list',
  standalone: true,
  imports: [CommonModule, RouterModule, PaginatePipe, PaginationComponent],
  templateUrl: './invoice-list.component.html',
})
export class SalesInvoiceListComponent implements OnInit {
  invoices: any[] = [];
  loading = true;
  error = '';
  activeTab: 'ALL' | 'DRAFT' | 'POSTED' | 'PAID' | 'VOID' = 'ALL';
  page = 1;
  pageSize = 25;

  constructor(private receivables: ReceivablesService) {}

  async ngOnInit() { await this.load(); }

  async load() {
    this.loading = true;
    try {
      const params = this.activeTab !== 'ALL' ? { status: this.activeTab } : {};
      const data = await this.receivables.getInvoices(params);
      this.invoices = data.results ?? data;
    } catch { this.error = 'Failed to load invoices.'; }
    finally { this.loading = false; }
  }

  async setTab(tab: string) {
    this.activeTab = tab as typeof this.activeTab;
    this.page = 1;
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

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      const response = await axios.get(`${API_ROOT}receivables/invoices/export/`, {
        params: { format }, responseType: 'blob',
      });
      const blob = new Blob([response.data], { type: response.headers['content-type'] });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sales-invoices.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
