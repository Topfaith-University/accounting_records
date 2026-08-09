import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { BanksService } from '../../services/banks.service';
import { BankTransactionsService } from '../../services/bank-transactions.service';

@Component({
  selector: 'app-bank-account-detail',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  templateUrl: './bank-account-detail.component.html',
})
export class BankAccountDetailComponent implements OnInit {
  account: any = null;
  reconciliations: any[] = [];
  transactions: any[] = [];
  loading = true;
  txnLoading = false;
  error = '';
  activeTab: 'reconciliations' | 'transactions' = 'reconciliations';
  showForm = false;
  formPeriodStart = '';
  formPeriodEnd = '';
  formStatementBalance = '';
  saving = false;
  formError = '';

  private id = '';

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private banksService: BanksService,
    private txnService: BankTransactionsService,
  ) {}

  async ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    try {
      const [account, reconciliations] = await Promise.all([
        this.banksService.getAccount(this.id),
        this.banksService.getAccountReconciliations(this.id),
      ]);
      this.account = account;
      this.reconciliations = reconciliations.results ?? reconciliations;
    } catch {
      this.error = 'Failed to load bank account details.';
    } finally {
      this.loading = false;
    }
  }

  async setTab(tab: 'reconciliations' | 'transactions') {
    this.activeTab = tab;
    if (tab === 'transactions' && this.transactions.length === 0) {
      this.txnLoading = true;
      try {
        const data = await this.txnService.getAll({ bankAccountId: this.id, page: 1, pageSize: 100 });
        this.transactions = data.results ?? data;
      } catch {
        // leave empty; user can retry by switching tabs
      } finally {
        this.txnLoading = false;
      }
    }
  }

  typeColor(type: string): string {
    const map: Record<string, string> = { RECEIPT: '#10b981', PAYMENT: '#ef4444', TRANSFER: '#3b82f6' };
    return map[type] ?? '#888';
  }

  toggleForm() {
    this.showForm = !this.showForm;
    this.formError = '';
    this.formPeriodStart = '';
    this.formPeriodEnd = '';
    this.formStatementBalance = '';
  }

  async submitCreate() {
    if (!this.formPeriodStart || !this.formPeriodEnd || !this.formStatementBalance) return;
    this.saving = true;
    this.formError = '';
    try {
      await this.banksService.createReconciliation({
        bank_account_id: this.id,
        period_start: this.formPeriodStart,
        period_end: this.formPeriodEnd,
        statement_balance: +this.formStatementBalance,
      });
      const data = await this.banksService.getAccountReconciliations(this.id);
      this.reconciliations = data.results ?? data;
      this.showForm = false;
      this.formPeriodStart = '';
      this.formPeriodEnd = '';
      this.formStatementBalance = '';
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to create reconciliation.');
    } finally {
      this.saving = false;
    }
  }

  statusColor(status: string): string {
    if (status === 'COMPLETED') return '#10b981';
    if (status === 'DRAFT') return '#f59e0b';
    return '#888';
  }
}
