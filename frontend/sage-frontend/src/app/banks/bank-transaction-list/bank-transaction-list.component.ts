import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { BankTransactionsService } from '../../services/bank-transactions.service';
import { BanksService } from '../../services/banks.service';
import { AccountsService } from '../../services/accounts.service';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-bank-transaction-list',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, BankSelectComponent, AccountSelectComponent, PaginatePipe, PaginationComponent],
  templateUrl: './bank-transaction-list.component.html',
})
export class BankTransactionListComponent implements OnInit {
  transactions: any[] = [];
  allBanks: any[] = [];
  allAccounts: any[] = [];
  selectedBankId = '';
  dateFrom = '';
  dateTo = '';
  loading = true;
  error = '';
  page = 1;
  pageSize = 25;

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
      const [txns, banks, accounts] = await Promise.all([
        this.txnService.getAll(),
        this.banksService.getAccounts(),
        this.accountsService.getAll(),
      ]);
      this.transactions = txns.results ?? txns;
      this.allBanks = banks.results ?? banks;
      this.allAccounts = accounts.results ?? accounts;
    } catch {
      this.error = 'Failed to load transactions.';
    } finally {
      this.loading = false;
    }
  }

  async applyFilter() {
    this.page = 1;
    this.loading = true;
    this.error = '';
    try {
      const data = await this.txnService.getAll(
        this.selectedBankId || undefined,
        this.dateFrom || undefined,
        this.dateTo || undefined,
      );
      this.transactions = data.results ?? data;
    } catch {
      this.error = 'Failed to filter transactions.';
    } finally {
      this.loading = false;
    }
  }

  clearFilter() {
    this.selectedBankId = '';
    this.dateFrom = '';
    this.dateTo = '';
    this.applyFilter();
  }

  get hasFilter(): boolean {
    return !!(this.selectedBankId || this.dateFrom || this.dateTo);
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
