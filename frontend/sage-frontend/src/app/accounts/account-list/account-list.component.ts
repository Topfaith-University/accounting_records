import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AccountsService } from '../../services/accounts.service';

@Component({
  selector: 'app-account-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './account-list.component.html',
})
export class AccountListComponent implements OnInit {
  accounts: any[] = [];
  loading = true;
  error = '';

  constructor(private accountsService: AccountsService) {}

  async ngOnInit() {
    try {
      const data = await this.accountsService.getAll();
      this.accounts = data.results ?? data;
    } catch {
      this.error = 'Failed to load accounts.';
    } finally {
      this.loading = false;
    }
  }
}
