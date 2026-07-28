import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { AccountsService } from '../../services/accounts.service';

@Component({
  selector: 'app-account-detail',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './account-detail.component.html',
})
export class AccountDetailComponent implements OnInit {
  account: any = null;
  entries: any[] = [];
  loading = true;
  ledgerLoading = false;
  error = '';
  ledgerError = '';
  private id = '';

  constructor(private route: ActivatedRoute, private accountsService: AccountsService) {}

  async ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    try {
      this.account = await this.accountsService.getById(this.id);
    } catch {
      this.error = 'Account not found.';
    } finally {
      this.loading = false;
    }
    if (this.account) {
      this.ledgerLoading = true;
      try {
        const data = await this.accountsService.getLedger(this.id);
        this.entries = data.entries ?? [];
      } catch {
        this.ledgerError = 'Failed to load ledger entries.';
      } finally {
        this.ledgerLoading = false;
      }
    }
  }

  entryTypeBadgeStyle(type: string): Record<string, string> {
    const styles: Record<string, Record<string, string>> = {
      MANUAL:           { background: '#F3F4F6', color: '#6B7280' },
      BANK_TRANSACTION: { background: '#EFF6FF', color: '#1D4ED8' },
      AP_PAYMENT:       { background: '#FFF7ED', color: '#C2410C' },
      AR_RECEIPT:       { background: '#F0FDF4', color: '#15803D' },
    };
    return {
      ...(styles[type] ?? styles['MANUAL']),
      display: 'inline-block', padding: '.15rem .5rem',
      borderRadius: '4px', fontSize: '.75rem', fontWeight: '700',
      textTransform: 'uppercase', letterSpacing: '.04em',
    };
  }
}
