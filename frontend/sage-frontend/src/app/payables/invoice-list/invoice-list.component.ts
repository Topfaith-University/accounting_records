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
}
