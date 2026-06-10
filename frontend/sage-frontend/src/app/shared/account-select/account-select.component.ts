import {
  Component, Input, Output, EventEmitter, OnInit,
  HostListener, ElementRef, forwardRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NG_VALUE_ACCESSOR, ControlValueAccessor } from '@angular/forms';
import { AccountsService } from '../../services/accounts.service';

interface Account {
  account_id: string;
  code: string;
  name: string;
  account_type: string;
  normal_balance?: string;
}

@Component({
  selector: 'app-account-select',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './account-select.component.html',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => AccountSelectComponent),
    multi: true,
  }],
})
export class AccountSelectComponent implements OnInit, ControlValueAccessor {
  @Input() label = 'Account';
  @Input() placeholder = 'Search or create account…';
  @Input() allAccounts: Account[] = [];

  @Output() accountsChanged = new EventEmitter<Account[]>();

  searchText = '';
  showDropdown = false;
  showModal = false;
  filteredAccounts: Account[] = [];

  newAccount = { name: '', account_type: '', description: '' };
  accountTypes = ['Assets', 'Liabilities', 'Equity', 'Revenue', 'Expenses', 'Cost of Sales'];
  creatingAccount = false;
  createError = '';

  selectedAccount: Account | null = null;

  private onChange: (val: string) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(
    private accountsService: AccountsService,
    private elRef: ElementRef,
  ) {}

  async ngOnInit() {
    if (this.allAccounts.length === 0) {
      try {
        const data = await this.accountsService.getAll();
        this.allAccounts = data.results ?? data;
      } catch { /* parent may pass allAccounts directly */ }
    }
    this.filteredAccounts = [...this.allAccounts];
  }

  get normalBalancePreview(): string {
    const map: Record<string, string> = {
      Assets: 'DEBIT', Expenses: 'DEBIT', 'Cost of Sales': 'DEBIT',
      Liabilities: 'CREDIT', Equity: 'CREDIT', Revenue: 'CREDIT',
    };
    return this.newAccount.account_type ? (map[this.newAccount.account_type] ?? '') : '';
  }

  writeValue(id: string) {
    const found = this.allAccounts.find(a => a.account_id === id) ?? null;
    this.selectedAccount = found;
    this.searchText = found ? `${found.code} — ${found.name}` : '';
  }

  registerOnChange(fn: (val: string) => void) { this.onChange = fn; }
  registerOnTouched(fn: () => void) { this.onTouched = fn; }

  onInput() {
    this.showDropdown = true;
    const q = this.searchText.toLowerCase();
    this.filteredAccounts = this.allAccounts.filter(
      a => a.name.toLowerCase().includes(q) || a.code.toLowerCase().includes(q)
    );
    if (!this.filteredAccounts.find(a => `${a.code} — ${a.name}` === this.searchText)) {
      this.selectedAccount = null;
      this.onChange('');
    }
  }

  selectAccount(acct: Account) {
    this.selectedAccount = acct;
    this.searchText = `${acct.code} — ${acct.name}`;
    this.showDropdown = false;
    this.onChange(acct.account_id);
    this.onTouched();
  }

  openCreateModal() {
    this.showDropdown = false;
    this.newAccount = { name: this.searchText.includes('—') ? '' : this.searchText, account_type: '', description: '' };
    this.createError = '';
    this.showModal = true;
  }

  async createAndSelect() {
    if (!this.newAccount.name || !this.newAccount.account_type) return;
    this.creatingAccount = true;
    this.createError = '';
    try {
      const created: Account = await this.accountsService.create({
        name: this.newAccount.name,
        account_type: this.newAccount.account_type,
        description: this.newAccount.description,
      });
      this.allAccounts = [...this.allAccounts, created];
      this.filteredAccounts = [...this.allAccounts];
      this.accountsChanged.emit(this.allAccounts);
      this.selectAccount(created);
      this.showModal = false;
    } catch (e: any) {
      this.createError = e.response?.data?.name?.[0] ?? e.response?.data?.detail ?? 'Failed to create account.';
    } finally {
      this.creatingAccount = false;
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    if (!this.elRef.nativeElement.contains(event.target)) {
      this.showDropdown = false;
    }
  }
}
