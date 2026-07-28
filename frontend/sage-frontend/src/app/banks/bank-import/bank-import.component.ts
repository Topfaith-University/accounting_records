import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { BankTransactionsService } from '../../services/bank-transactions.service';
import { BanksService } from '../../services/banks.service';
import { AccountsService } from '../../services/accounts.service';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';

@Component({
  selector: 'app-bank-import',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, BankSelectComponent, AccountSelectComponent],
  templateUrl: './bank-import.component.html',
})
export class BankImportComponent implements OnInit {
  allBanks: any[] = [];
  allAccounts: any[] = [];

  bankAccountId = '';
  defaultAccountId = '';
  importFileType = 'CSV';
  dateFormat = 'dd/mm/yyyy';
  dateRangeType = 'ALL';
  dateFrom = '';
  dateTo = '';
  selectedFile: File | null = null;
  fileName = '';

  importing = false;
  result: { created: number; skipped: number; errors: string[] } | null = null;
  error = '';

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
    } catch {
      this.error = 'Failed to load bank accounts or GL accounts.';
    }
  }

  onFileChange(event: Event) {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
    this.fileName = this.selectedFile?.name ?? '';
  }

  get canImport(): boolean {
    const dateRangeOk = this.dateRangeType === 'ALL' || (!!this.dateFrom && !!this.dateTo);
    return !this.importing && !!this.bankAccountId && !!this.defaultAccountId && !!this.selectedFile && dateRangeOk;
  }

  async importFile() {
    if (!this.canImport) return;
    this.importing = true;
    this.result = null;
    this.error = '';
    const fd = new FormData();
    fd.append('bank_account_id', this.bankAccountId);
    fd.append('default_account_id', this.defaultAccountId);
    fd.append('date_format', this.dateFormat);
    fd.append('date_range_type', this.dateRangeType);
    if (this.dateRangeType === 'DATE_RANGE') {
      fd.append('date_from', this.dateFrom);
      fd.append('date_to', this.dateTo);
    }
    fd.append('file', this.selectedFile!);
    try {
      this.result = await this.txnService.importCsv(fd);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Import failed.';
    } finally {
      this.importing = false;
    }
  }
}
