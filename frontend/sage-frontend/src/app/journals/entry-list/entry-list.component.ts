import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { JournalsService } from '../../services/journals.service';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-entry-list',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, PaginationComponent],
  templateUrl: './entry-list.component.html',
})
export class EntryListComponent implements OnInit {
  entries: any[] = [];
  loading = true;
  error = '';
  activeTab: 'ALL' | 'DRAFT' | 'POSTED' | 'VOID' = 'ALL';
  tabs: ('ALL' | 'DRAFT' | 'POSTED' | 'VOID')[] = ['ALL', 'DRAFT', 'POSTED', 'VOID'];
  dateFrom = '';
  dateTo = '';
  search = '';
  page = 1;
  pageSize = 25;
  total = 0;

  /** Incremented on every loadEntries() call; guards against a stale response overwriting a newer one. */
  private requestSeq = 0;
  /** Pending debounce timer for the search input; not used by date/tab filters, which apply immediately. */
  private searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private journalsService: JournalsService) {}

  async ngOnInit() { await this.loadEntries(); }

  async loadEntries() {
    const seq = ++this.requestSeq;
    this.loading = true;
    try {
      const params: { status?: string; date_from?: string; date_to?: string; search?: string; page: number; page_size: number } =
        { page: this.page, page_size: this.pageSize };
      if (this.activeTab !== 'ALL') params.status = this.activeTab;
      if (this.dateFrom) params.date_from = this.dateFrom;
      if (this.dateTo) params.date_to = this.dateTo;
      if (this.search.trim()) params.search = this.search.trim();
      const data = await this.journalsService.getEntries(params);
      if (seq !== this.requestSeq) return; // a newer request has since been issued — discard this stale response
      this.entries = data.results ?? data;
      this.total = data.count ?? data.results?.length ?? data.length ?? 0;
      this.error = '';
    } catch {
      if (seq !== this.requestSeq) return; // stale failure — don't clobber fresher successful results
      this.error = 'Failed to load journal entries.';
    } finally {
      if (seq === this.requestSeq) this.loading = false;
    }
  }

  async setTab(tab: string) {
    this.cancelSearchDebounce();
    this.activeTab = tab as typeof this.activeTab;
    this.page = 1;
    await this.loadEntries();
  }

  async applyFilters() {
    this.page = 1;
    await this.loadEntries();
  }

  /** Called on every keystroke in the search box; debounces the actual filter/reload by ~300ms. */
  onSearchChange() {
    this.cancelSearchDebounce();
    this.searchDebounceTimer = setTimeout(() => {
      this.searchDebounceTimer = null;
      this.applyFilters();
    }, 300);
  }

  private cancelSearchDebounce() {
    if (this.searchDebounceTimer !== null) {
      clearTimeout(this.searchDebounceTimer);
      this.searchDebounceTimer = null;
    }
  }

  async clearFilters() {
    this.cancelSearchDebounce();
    this.dateFrom = '';
    this.dateTo = '';
    this.search = '';
    await this.applyFilters();
  }

  get hasFilters(): boolean {
    return !!(this.dateFrom || this.dateTo || this.search);
  }

  async onPageChange(newPage: number) {
    this.page = newPage;
    await this.loadEntries();
  }

  statusColor(status: string) {
    return { DRAFT: '#f59e0b', POSTED: '#10b981', VOID: '#ef4444' }[status] ?? '#888';
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      const params: { date_from?: string; date_to?: string } = {};
      if (this.dateFrom) params.date_from = this.dateFrom;
      if (this.dateTo) params.date_to = this.dateTo;
      await this.journalsService.exportFile(format, params);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
