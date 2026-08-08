import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { BanksService } from '../../services/banks.service';
import { AccountsService } from '../../services/accounts.service';
import { AuthService } from '../../services/auth.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-bank-account-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, AccountSelectComponent, PaginatePipe, PaginationComponent],
  templateUrl: './bank-account-list.component.html',
})
export class BankAccountListComponent implements OnInit {
  accounts: any[] = [];
  glAccounts: any[] = [];
  allAccounts: any[] = [];
  loading = true;
  error = '';
  page = 1;
  pageSize = 25;
  search = '';

  showForm = false;
  saving = false;
  formError = '';
  editingBankAccountId: string | null = null;
  form = {
    name: '',
    account_number: '',
    bank_name: '',
    currency: 'NGN',
    opening_balance: 0,
    opening_balance_date: new Date().toISOString().slice(0, 10),
    gl_account_id_input: '',
  };

  get canManage(): boolean {
    return !!this.auth.getCurrentUser();
  }

  get isEditMode(): boolean {
    return !!this.editingBankAccountId;
  }

  get filteredAccounts(): any[] {
    const term = this.search.trim().toLowerCase();
    if (!term) return this.accounts;
    return this.accounts.filter(a =>
      (a.name ?? '').toLowerCase().includes(term)
      || (a.account_number ?? '').toLowerCase().includes(term)
      || (a.bank_name ?? '').toLowerCase().includes(term)
    );
  }

  constructor(
    private banksService: BanksService,
    private accountsService: AccountsService,
    private auth: AuthService,
  ) {}

  async ngOnInit() {
    await this.loadData();
  }

  async loadData() {
    try {
      const [bankData, glData] = await Promise.all([
        this.banksService.getAccounts(),
        this.accountsService.getAll(),
      ]);
      this.accounts = bankData.results ?? bankData;
      this.glAccounts = glData.results ?? glData;
      this.allAccounts = [...this.glAccounts];
    } catch {
      this.error = 'Failed to load bank accounts.';
    } finally {
      this.loading = false;
    }
  }

  toggleForm() {
    this.showForm = !this.showForm;
    this.editingBankAccountId = null;
    this.formError = '';
    this.form = {
      name: '',
      account_number: '',
      bank_name: '',
      currency: 'NGN',
      opening_balance: 0,
      opening_balance_date: new Date().toISOString().slice(0, 10),
      gl_account_id_input: '',
    };
  }

  onSearchChange() {
    this.page = 1;
  }

  startEdit(account: any) {
    this.showForm = true;
    this.editingBankAccountId = account.bank_account_id;
    this.formError = '';
    this.form = {
      name: account.name ?? '',
      account_number: account.account_number ?? '',
      bank_name: account.bank_name ?? '',
      currency: account.currency ?? 'NGN',
      opening_balance: account.opening_balance ?? 0,
      opening_balance_date: account.opening_balance_date ?? new Date().toISOString().slice(0, 10),
      gl_account_id_input: account.gl_account_id ?? '',
    };
  }

  cancelForm() {
    this.showForm = false;
    this.editingBankAccountId = null;
    this.formError = '';
    this.form = {
      name: '',
      account_number: '',
      bank_name: '',
      currency: 'NGN',
      opening_balance: 0,
      opening_balance_date: new Date().toISOString().slice(0, 10),
      gl_account_id_input: '',
    };
  }

  async submitForm() {
    if (!this.form.name || !this.form.bank_name || !this.form.opening_balance_date) return;
    this.saving = true;
    this.formError = '';
    try {
      if (this.editingBankAccountId) {
        await this.banksService.updateAccount(this.editingBankAccountId, this.form);
      } else {
        await this.banksService.createAccount(this.form);
      }
      await this.loadData();
      this.cancelForm();
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to save bank account.');
    } finally {
      this.saving = false;
    }
  }

  onGlAccountChange(id: string) {
    this.form.gl_account_id_input = id;
  }

  async deleteAccount(account: any) {
    if (!confirm(`Delete bank account "${account.name}"?`)) return;
    try {
      await this.banksService.deleteAccount(account.bank_account_id);
      await this.loadData();
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to delete bank account.');
    }
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      await this.banksService.exportFile(format);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
