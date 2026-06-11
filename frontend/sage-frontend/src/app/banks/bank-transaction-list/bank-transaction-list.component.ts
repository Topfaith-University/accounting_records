import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { BankTransactionsService } from '../../services/bank-transactions.service';
import { BanksService } from '../../services/banks.service';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';

@Component({
  selector: 'app-bank-transaction-list',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, BankSelectComponent],
  templateUrl: './bank-transaction-list.component.html',
})
export class BankTransactionListComponent implements OnInit {
  transactions: any[] = [];
  allBanks: any[] = [];
  selectedBankId = '';
  loading = true;
  error = '';

  constructor(
    private txnService: BankTransactionsService,
    private banksService: BanksService,
  ) {}

  async ngOnInit() {
    try {
      const [txns, banks] = await Promise.all([
        this.txnService.getAll(),
        this.banksService.getAccounts(),
      ]);
      this.transactions = txns.results ?? txns;
      this.allBanks = banks.results ?? banks;
    } catch {
      this.error = 'Failed to load transactions.';
    } finally {
      this.loading = false;
    }
  }

  async filterByBank() {
    this.loading = true;
    this.error = '';
    try {
      const data = await this.txnService.getAll(this.selectedBankId || undefined);
      this.transactions = data.results ?? data;
    } catch {
      this.error = 'Failed to filter transactions.';
    } finally {
      this.loading = false;
    }
  }

  typeColor(type: string): string {
    const map: Record<string, string> = {
      RECEIPT: '#10b981',
      PAYMENT: '#ef4444',
      TRANSFER: '#3b82f6',
    };
    return map[type] ?? '#888';
  }
}
