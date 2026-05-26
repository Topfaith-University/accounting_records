import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AccountsService } from '../../services/accounts.service';
import { AuthService } from '../../services/auth.service';

const DEBIT_NORMAL_TYPES = new Set([
  'Cost of Sales', 'Expenses', 'Income Tax', 'Non-Current Assets', 'Current Assets'
]);

@Component({
  selector: 'app-account-list',
  standalone: true,
  imports: [CommonModule, FormsModule],
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
  form = { code: '', name: '', account_type: '', description: '' };

  get canCreate(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Admin', 'Manager'].includes(r)) ?? false;
  }

  get normalBalancePreview(): string {
    return DEBIT_NORMAL_TYPES.has(this.form.account_type) ? 'Debit' : 'Credit';
  }

  constructor(private accountsService: AccountsService, private auth: AuthService) {}

  async ngOnInit() {
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
    this.formError = '';
    this.form = { code: '', name: '', account_type: this.accountTypes[0] ?? '', description: '' };
  }

  async submitCreate() {
    if (!this.form.code || !this.form.name || !this.form.account_type) return;
    this.saving = true;
    this.formError = '';
    try {
      await this.accountsService.create({
        ...this.form,
        normal_balance: DEBIT_NORMAL_TYPES.has(this.form.account_type) ? 'DEBIT' : 'CREDIT',
      });
      const data = await this.accountsService.getAll();
      this.accounts = data.results ?? data;
      this.showForm = false;
      this.form = { code: '', name: '', account_type: '', description: '' };
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Failed to create account.';
    } finally {
      this.saving = false;
    }
  }
}
