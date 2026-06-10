import {
  Component, Input, Output, EventEmitter, OnInit,
  HostListener, ElementRef, forwardRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NG_VALUE_ACCESSOR, ControlValueAccessor } from '@angular/forms';
import { BanksService } from '../../services/banks.service';
import { AccountSelectComponent } from '../account-select/account-select.component';

interface BankAccount {
  bank_account_id: string;
  name: string;
  bank_name: string;
  account_number?: string;
}

@Component({
  selector: 'app-bank-select',
  standalone: true,
  imports: [CommonModule, FormsModule, AccountSelectComponent],
  templateUrl: './bank-select.component.html',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => BankSelectComponent),
    multi: true,
  }],
})
export class BankSelectComponent implements OnInit, ControlValueAccessor {
  @Input() label = 'Bank Account';
  @Input() placeholder = 'Search or create bank account…';
  @Input() allBanks: BankAccount[] = [];
  @Input() excludeId = '';

  @Output() banksChanged = new EventEmitter<BankAccount[]>();

  searchText = '';
  showDropdown = false;
  showModal = false;
  filteredBanks: BankAccount[] = [];

  newBank = {
    name: '',
    bank_name: '',
    account_number: '',
    opening_balance: 0,
    opening_balance_date: new Date().toISOString().slice(0, 10),
    gl_account_id: '',
  };
  creatingBank = false;
  createError = '';

  selectedBank: BankAccount | null = null;

  private onChange: (val: string) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(
    private banksService: BanksService,
    private elRef: ElementRef,
  ) {}

  async ngOnInit() {
    if (this.allBanks.length === 0) {
      try {
        const data = await this.banksService.getAccounts();
        this.allBanks = data.results ?? data;
      } catch {}
    }
    this.refreshFiltered();
  }

  private refreshFiltered() {
    this.filteredBanks = this.allBanks.filter(b => b.bank_account_id !== this.excludeId);
  }

  writeValue(id: string) {
    const found = this.allBanks.find(b => b.bank_account_id === id) ?? null;
    this.selectedBank = found;
    this.searchText = found ? found.name : '';
  }

  registerOnChange(fn: (val: string) => void) { this.onChange = fn; }
  registerOnTouched(fn: () => void) { this.onTouched = fn; }

  onInput() {
    this.showDropdown = true;
    const q = this.searchText.toLowerCase();
    this.filteredBanks = this.allBanks
      .filter(b => b.bank_account_id !== this.excludeId)
      .filter(b => b.name.toLowerCase().includes(q) || b.bank_name.toLowerCase().includes(q));
    if (!this.filteredBanks.find(b => b.name === this.searchText)) {
      this.selectedBank = null;
      this.onChange('');
    }
  }

  selectBank(bank: BankAccount) {
    this.selectedBank = bank;
    this.searchText = bank.name;
    this.showDropdown = false;
    this.onChange(bank.bank_account_id);
    this.onTouched();
  }

  openCreateModal() {
    this.showDropdown = false;
    this.newBank = {
      name: this.searchText.trim(),
      bank_name: '',
      account_number: '',
      opening_balance: 0,
      opening_balance_date: new Date().toISOString().slice(0, 10),
      gl_account_id: '',
    };
    this.createError = '';
    this.showModal = true;
  }

  onGlAccountChange(id: string) {
    this.newBank.gl_account_id = id;
  }

  async createAndSelect() {
    if (!this.newBank.name || !this.newBank.bank_name || !this.newBank.opening_balance_date) return;
    this.creatingBank = true;
    this.createError = '';
    try {
      const payload: any = {
        name: this.newBank.name,
        bank_name: this.newBank.bank_name,
        account_number: this.newBank.account_number,
        opening_balance: this.newBank.opening_balance,
        opening_balance_date: this.newBank.opening_balance_date,
      };
      if (this.newBank.gl_account_id) payload.gl_account_id = this.newBank.gl_account_id;
      const created: BankAccount = await this.banksService.createAccount(payload);
      this.allBanks = [...this.allBanks, created];
      this.refreshFiltered();
      this.banksChanged.emit(this.allBanks);
      this.selectBank(created);
      this.showModal = false;
    } catch (e: any) {
      this.createError = e.response?.data?.name?.[0] ?? e.response?.data?.detail ?? 'Failed to create bank account.';
    } finally {
      this.creatingBank = false;
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    if (!this.elRef.nativeElement.contains(event.target)) {
      this.showDropdown = false;
    }
  }
}
