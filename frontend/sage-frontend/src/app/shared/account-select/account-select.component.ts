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

const DEBIT_NORMAL_TYPES = new Set([
  'Cost of Sales', 'Expenses', 'Income Tax', 'Non-Current Assets', 'Current Assets'
]);

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
  accountTypes: string[] = [];
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
    try {
      if (this.allAccounts.length === 0) {
        const data = await this.accountsService.getAll();
        this.allAccounts = data.results ?? data;
      }
      const typeData = await this.accountsService.getTypes();
      this.accountTypes = typeData.account_types ?? [];
    } catch { /* parent may pass allAccounts directly */ }
    this.filteredAccounts = [...this.allAccounts];
  }

  get normalBalancePreview(): string {
    if (!this.newAccount.account_type) return '';
    return DEBIT_NORMAL_TYPES.has(this.newAccount.account_type) ? 'DEBIT' : 'CREDIT';
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
        normal_balance: DEBIT_NORMAL_TYPES.has(this.newAccount.account_type) ? 'DEBIT' : 'CREDIT',
        description: this.newAccount.description,
      });
      this.allAccounts = [...this.allAccounts, created];
      this.filteredAccounts = [...this.allAccounts];
      this.accountsChanged.emit(this.allAccounts);
      this.selectAccount(created);
      this.showModal = false;
    } catch (e: any) {
      this.createError = e.response?.data?.detail
        ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to create account.');
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
