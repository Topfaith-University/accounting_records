import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { AccountsService } from '../../services/accounts.service';
import { AuthService } from '../../services/auth.service';

const DEBIT_NORMAL_TYPES = new Set([
  'Cost of Sales', 'Expenses', 'Income Tax', 'Non-Current Assets', 'Current Assets'
]);

@Component({
  selector: 'app-account-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './account-list.component.html',
})
export class AccountListComponent implements OnInit {
  accounts: any[] = [];
  accountTypes: string[] = [];
  loading = true;
  error = '';

  showForm = false;
  saving = false;
  formError = '';
  editingAccountId: string | null = null;
  form = { name: '', account_type: '', description: '' };

  get canManage(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Admin', 'Manager'].includes(r)) ?? false;
  }

  get canDelete(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.includes('Admin') ?? false;
  }

  get normalBalancePreview(): string {
    return DEBIT_NORMAL_TYPES.has(this.form.account_type) ? 'Debit' : 'Credit';
  }

  get isEditMode(): boolean {
    return !!this.editingAccountId;
  }

  constructor(private accountsService: AccountsService, private auth: AuthService) {}

  async ngOnInit() {
    await this.loadAccounts();
  }

  async loadAccounts() {
    try {
      const [accountData, typeData] = await Promise.all([
        this.accountsService.getAll(),
        this.accountsService.getTypes(),
      ]);
      this.accounts = accountData.results ?? accountData;
      this.accountTypes = typeData.account_types ?? [];
    } catch {
      this.error = 'Failed to load accounts.';
    } finally {
      this.loading = false;
    }
  }

  toggleForm() {
    this.showForm = !this.showForm;
    this.editingAccountId = null;
    this.formError = '';
    this.form = { name: '', account_type: this.accountTypes[0] ?? '', description: '' };
  }

  startEdit(account: any) {
    this.showForm = true;
    this.editingAccountId = account.account_id;
    this.formError = '';
    this.form = {
      name: account.name ?? '',
      account_type: account.account_type ?? this.accountTypes[0] ?? '',
      description: account.description ?? '',
    };
  }

  cancelForm() {
    this.showForm = false;
    this.editingAccountId = null;
    this.formError = '';
    this.form = { name: '', account_type: this.accountTypes[0] ?? '', description: '' };
  }

  async submitForm() {
    if (!this.form.name || !this.form.account_type) return;
    this.saving = true;
    this.formError = '';
    try {
      const payload = {
        ...this.form,
        normal_balance: DEBIT_NORMAL_TYPES.has(this.form.account_type) ? 'DEBIT' : 'CREDIT',
      };
      if (this.editingAccountId) {
        await this.accountsService.update(this.editingAccountId, payload);
      } else {
        await this.accountsService.create(payload);
      }
      await this.loadAccounts();
      this.cancelForm();
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to save account.');
    } finally {
      this.saving = false;
    }
  }

  async deleteAccount(account: any) {
    if (!confirm(`Delete account "${account.name}"?`)) return;
    try {
      await this.accountsService.delete(account.account_id);
      await this.loadAccounts();
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to delete account.');
    }
  }
}
