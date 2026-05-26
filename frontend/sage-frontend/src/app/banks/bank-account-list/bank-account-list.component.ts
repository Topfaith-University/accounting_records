import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { BanksService } from '../../services/banks.service';
import { AccountsService } from '../../services/accounts.service';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-bank-account-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './bank-account-list.component.html',
})
export class BankAccountListComponent implements OnInit {
  accounts: any[] = [];
  glAccounts: any[] = [];
  loading = true;
  error = '';

  showForm = false;
  saving = false;
  formError = '';
  form = {
    name: '',
    account_number: '',
    bank_name: '',
    currency: 'NGN',
    opening_balance: 0,
    opening_balance_date: new Date().toISOString().slice(0, 10),
    gl_account_id_input: '',
  };

  get canCreate(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Admin', 'Manager'].includes(r)) ?? false;
  }

  constructor(
    private banksService: BanksService,
    private accountsService: AccountsService,
    private auth: AuthService,
  ) {}

  async ngOnInit() {
    try {
      const [bankData, glData] = await Promise.all([
        this.banksService.getAccounts(),
        this.accountsService.getAll(),
      ]);
      this.accounts = bankData.results ?? bankData;
      this.glAccounts = glData.results ?? glData;
    } catch {
      this.error = 'Failed to load bank accounts.';
    } finally {
      this.loading = false;
    }
  }

  toggleForm() {
    this.showForm = !this.showForm;
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

  async submitCreate() {
    if (!this.form.name || !this.form.bank_name || !this.form.opening_balance_date) return;
    this.saving = true;
    this.formError = '';
    try {
      await this.banksService.createAccount(this.form);
      const data = await this.banksService.getAccounts();
      this.accounts = data.results ?? data;
      this.showForm = false;
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Failed to create bank account.';
    } finally {
      this.saving = false;
    }
  }
}
