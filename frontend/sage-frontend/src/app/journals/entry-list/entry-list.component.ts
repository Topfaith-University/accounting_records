import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { JournalsService } from '../../services/journals.service';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-entry-list',
  standalone: true,
  imports: [CommonModule, RouterModule, PaginatePipe, PaginationComponent],
  templateUrl: './entry-list.component.html',
})
export class EntryListComponent implements OnInit {
  entries: any[] = [];
  loading = true;
  error = '';
  activeTab: 'ALL' | 'DRAFT' | 'POSTED' | 'VOID' = 'ALL';
  tabs: ('ALL' | 'DRAFT' | 'POSTED' | 'VOID')[] = ['ALL', 'DRAFT', 'POSTED', 'VOID'];
  page = 1;
  pageSize = 25;

  constructor(private journalsService: JournalsService) {}

  async ngOnInit() { await this.loadEntries(); }

  async loadEntries() {
    this.loading = true;
    try {
      const params = this.activeTab !== 'ALL' ? { status: this.activeTab } : {};
      const data = await this.journalsService.getEntries(params);
      this.entries = data.results ?? data;
    } catch { this.error = 'Failed to load journal entries.'; }
    finally { this.loading = false; }
  }

  async setTab(tab: string) {
    this.activeTab = tab as typeof this.activeTab;
    this.page = 1;
    await this.loadEntries();
  }

  statusColor(status: string) {
    return { DRAFT: '#f59e0b', POSTED: '#10b981', VOID: '#ef4444' }[status] ?? '#888';
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      await this.journalsService.exportFile(format);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
