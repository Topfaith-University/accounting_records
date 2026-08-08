import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { BankTransactionsService } from '../../services/bank-transactions.service';
import { BanksService } from '../../services/banks.service';
import { AccountsService } from '../../services/accounts.service';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-bank-transaction-list',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, BankSelectComponent, AccountSelectComponent, PaginationComponent],
  templateUrl: './bank-transaction-list.component.html',
})
export class BankTransactionListComponent implements OnInit {
  transactions: any[] = [];
  allBanks: any[] = [];
  allAccounts: any[] = [];
  selectedBankId = '';
  dateFrom = '';
  dateTo = '';
  search = '';
  private requestSeq = 0;
  private searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  loading = true;
  error = '';
  page = 1;
  pageSize = 25;
  total = 0;

  // Import panel state
  showImportPanel = false;
  importBankId = '';
  importAccountId = '';
  importDateFormat = 'dd/mm/yyyy';
  importDateRangeType = 'ALL';
  importDateFrom = '';
  importDateTo = '';
  importSelectedFile: File | null = null;
  importFileName = '';
  importing = false;
  importResult: { created: number; skipped: number; errors: string[] } | null = null;
  importError = '';

  constructor(
    private txnService: BankTransactionsService,
    private banksService: BanksService,
    private accountsService: AccountsService,
  ) {}

  async ngOnInit() {
    try {
      const [banks, accounts] = await Promise.all([
        this.banksService.getAccounts(),
        this.accountsService.getAll(),
      ]);
      this.allBanks = banks.results ?? banks;
      this.allAccounts = accounts.results ?? accounts;
      await this.loadTransactions();
    } catch {
      this.error = 'Failed to load transactions.';
      this.loading = false;
    }
  }

  private async loadTransactions() {
    this.loading = true;
    this.error = '';
    const seq = ++this.requestSeq;
    try {
      const data = await this.txnService.getAll({
        bankAccountId: this.selectedBankId || undefined,
        dateFrom: this.dateFrom || undefined,
        dateTo: this.dateTo || undefined,
        search: this.search.trim() || undefined,
        page: this.page,
        pageSize: this.pageSize,
      });
      if (seq !== this.requestSeq) return;
      this.transactions = data.results ?? data;
      this.total = data.count ?? data.results?.length ?? data.length ?? 0;
    } catch {
      if (seq !== this.requestSeq) return;
      this.error = 'Failed to load transactions.';
    } finally {
      if (seq === this.requestSeq) this.loading = false;
    }
  }

  async applyFilter() {
    this.page = 1;
    await this.loadTransactions();
  }

  async onPageChange(newPage: number) {
    this.page = newPage;
    await this.loadTransactions();
  }

  onSearchChange() {
    this.cancelSearchDebounce();
    this.searchDebounceTimer = setTimeout(() => {
      this.searchDebounceTimer = null;
      this.applyFilter();
    }, 300);
  }

  private cancelSearchDebounce() {
    if (this.searchDebounceTimer !== null) {
      clearTimeout(this.searchDebounceTimer);
      this.searchDebounceTimer = null;
    }
  }

  clearFilter() {
    this.cancelSearchDebounce();
    this.selectedBankId = '';
    this.dateFrom = '';
    this.dateTo = '';
    this.search = '';
    this.applyFilter();
  }

  get hasFilter(): boolean {
    return !!(this.selectedBankId || this.dateFrom || this.dateTo || this.search);
  }

  // ── Import panel ──────────────────────────────────────────

  toggleImportPanel() {
    this.showImportPanel = !this.showImportPanel;
    if (this.showImportPanel) {
      this.importBankId = this.selectedBankId;
      this.importResult = null;
      this.importError = '';
    }
  }

  onImportFileChange(event: Event) {
    const input = event.target as HTMLInputElement;
    this.importSelectedFile = input.files?.[0] ?? null;
    this.importFileName = this.importSelectedFile?.name ?? '';
  }

  get canImport(): boolean {
    const dateOk = this.importDateRangeType === 'ALL' || (!!this.importDateFrom && !!this.importDateTo);
    return !this.importing && !!this.importBankId && !!this.importAccountId && !!this.importSelectedFile && dateOk;
  }

  async runImport() {
    if (!this.canImport) return;
    this.importing = true;
    this.importResult = null;
    this.importError = '';
    const fd = new FormData();
    fd.append('bank_account_id', this.importBankId);
    fd.append('default_account_id', this.importAccountId);
    fd.append('date_format', this.importDateFormat);
    fd.append('date_range_type', this.importDateRangeType);
    if (this.importDateRangeType === 'DATE_RANGE') {
      fd.append('date_from', this.importDateFrom);
      fd.append('date_to', this.importDateTo);
    }
    fd.append('file', this.importSelectedFile!);
    try {
      this.importResult = await this.txnService.importCsv(fd);
      if ((this.importResult?.created ?? 0) > 0) {
        await this.applyFilter();
      }
    } catch (e: any) {
      this.importError = e.response?.data?.detail ?? 'Import failed.';
    } finally {
      this.importing = false;
    }
  }

  // ── Export ────────────────────────────────────────────────

  async exportFile(format: 'csv' | 'xlsx') {
    const params: Record<string, string> = {};
    if (this.selectedBankId) params['bank_account_id'] = this.selectedBankId;
    if (this.dateFrom) params['date_from'] = this.dateFrom;
    if (this.dateTo) params['date_to'] = this.dateTo;
    const ext = format === 'xlsx' ? 'xlsx' : 'csv';
    try {
      await this.txnService.exportFile(params, format, `bank-transactions.${ext}`);
    } catch {
      this.error = 'Export failed.';
    }
  }

  typeColor(type: string): string {
    const map: Record<string, string> = {
      RECEIPT: 'var(--success)',
      PAYMENT: 'var(--danger)',
      TRANSFER: 'var(--navy-primary)',
    };
    return map[type] ?? 'var(--text-muted)';
  }
}
