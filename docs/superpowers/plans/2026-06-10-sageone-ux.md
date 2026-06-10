# SageOne UX Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Sage app in line with SageOne's UX: searchable account/bank selectors with inline quick-create, a simplified journal entry form (Debit/Credit columns), a dedicated Banking sidebar section, and a general SageOne alignment sweep.

**Architecture:** Two new reusable Angular standalone components (`AccountSelectComponent`, `BankSelectComponent`) replace all plain `<select>` dropdowns throughout the app. The shell nav is restructured to separate "Ledger" from "Banking". The journal entry form is redesigned in-place. A final alignment sweep adds confirm dialogs, consistent empty-states, and style normalisation.

**Tech Stack:** Angular 17 (standalone components), TypeScript, axios (via `AccountsService`/`BanksService`), inline CSS using existing CSS variables (`var(--navy-primary)`, `var(--border)`, `var(--radius-sm)`, etc.). No new npm packages.

---

## File Map

| Action | File |
|--------|------|
| Create | `frontend/sage-frontend/src/app/shared/account-select/account-select.component.ts` |
| Create | `frontend/sage-frontend/src/app/shared/account-select/account-select.component.html` |
| Create | `frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.ts` |
| Create | `frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.html` |
| Modify | `frontend/sage-frontend/src/app/shell/shell.component.html` |
| Modify | `frontend/sage-frontend/src/app/shell/shell.component.ts` |
| Modify | `frontend/sage-frontend/src/app/journals/entry-form/entry-form.component.ts` |
| Modify | `frontend/sage-frontend/src/app/journals/entry-form/entry-form.component.html` |
| Modify | `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.ts` |
| Modify | `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.html` |
| Modify | `frontend/sage-frontend/src/app/payables/invoice-form/invoice-form.component.ts` |
| Modify | `frontend/sage-frontend/src/app/payables/invoice-form/invoice-form.component.html` |
| Modify | `frontend/sage-frontend/src/app/receivables/invoice-form/invoice-form.component.ts` |
| Modify | `frontend/sage-frontend/src/app/receivables/invoice-form/invoice-form.component.html` |
| Modify | `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.html` |
| Modify | `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.ts` |
| Modify | `frontend/sage-frontend/src/app/accounts/account-list/account-list.component.html` |
| Modify | `frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.html` |
| Modify | `frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.html` |
| Modify | `frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.html` |
| Modify | `frontend/sage-frontend/src/app/payables/invoice-list/invoice-list.component.html` |
| Modify | `frontend/sage-frontend/src/app/receivables/invoice-list/invoice-list.component.html` |

---

## Task 1: Create `AccountSelectComponent`

**Files:**
- Create: `frontend/sage-frontend/src/app/shared/account-select/account-select.component.ts`
- Create: `frontend/sage-frontend/src/app/shared/account-select/account-select.component.html`

This component is a searchable typeahead that replaces plain `<select>` for GL accounts. It loads all accounts once on init, filters locally as the user types, shows a dropdown, and offers inline quick-create.

- [ ] **Step 1: Create the component TS file**

```typescript
// frontend/sage-frontend/src/app/shared/account-select/account-select.component.ts
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
```

- [ ] **Step 2: Create the component HTML file**

```html
<!-- frontend/sage-frontend/src/app/shared/account-select/account-select.component.html -->
<div style="position:relative">
  <input
    type="text"
    [(ngModel)]="searchText"
    (input)="onInput()"
    (focus)="showDropdown = true"
    [placeholder]="placeholder"
    autocomplete="off"
    style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box;background:var(--white)"
  />

  @if (showDropdown) {
    <div style="position:absolute;z-index:1000;top:100%;left:0;right:0;background:var(--white);border:1.5px solid var(--border);border-radius:var(--radius-sm);box-shadow:0 4px 16px rgba(0,0,0,.12);max-height:220px;overflow-y:auto;margin-top:2px">
      @for (acct of filteredAccounts; track acct.account_id) {
        <div
          (mousedown)="selectAccount(acct)"
          style="padding:.5rem .75rem;cursor:pointer;font-size:.875rem;border-bottom:1px solid var(--border)"
          onmouseover="this.style.background='var(--navy-subtle)'"
          onmouseout="this.style.background=''"
        >
          <span style="font-family:var(--font-mono);color:var(--text-muted);font-size:.8rem">{{ acct.code }}</span>
          &nbsp;{{ acct.name }}
          <span style="float:right;font-size:.75rem;color:var(--text-muted)">{{ acct.account_type }}</span>
        </div>
      }
      @if (filteredAccounts.length === 0) {
        <div style="padding:.5rem .75rem;font-size:.875rem;color:var(--text-muted);font-style:italic">No accounts match "{{ searchText }}"</div>
      }
      <div
        (mousedown)="openCreateModal()"
        style="padding:.5rem .75rem;cursor:pointer;font-size:.875rem;color:var(--navy-primary);font-weight:700;border-top:1.5px solid var(--border)"
        onmouseover="this.style.background='var(--navy-subtle)'"
        onmouseout="this.style.background=''"
      >
        + Create account…
      </div>
    </div>
  }
</div>

<!-- Quick-create modal -->
@if (showModal) {
  <div style="position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:2000;display:flex;align-items:center;justify-content:center" (click)="showModal = false">
    <div style="background:var(--white);border-radius:var(--radius-lg);padding:1.5rem;width:420px;max-width:95vw;box-shadow:0 8px 32px rgba(0,0,0,.18)" (click)="$event.stopPropagation()">
      <h3 style="margin:0 0 1.25rem;font-size:1.05rem;font-weight:700;color:var(--navy-deep)">New Account</h3>
      @if (createError) {
        <p style="color:var(--danger);font-size:.85rem;margin:0 0 .75rem;padding:.5rem;background:rgba(239,68,68,.08);border-radius:var(--radius-sm)">{{ createError }}</p>
      }
      <div style="display:flex;flex-direction:column;gap:.75rem">
        <div>
          <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Name *</label>
          <input [(ngModel)]="newAccount.name" placeholder="Account name" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
        </div>
        <div>
          <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Type *</label>
          <select [(ngModel)]="newAccount.account_type" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box">
            <option value="">— select type —</option>
            @for (t of accountTypes; track t) {
              <option [value]="t">{{ t }}</option>
            }
          </select>
        </div>
        <div>
          <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Normal Balance</label>
          <div style="padding:.5rem .75rem;background:var(--navy-subtle);border-radius:var(--radius-sm);font-size:.875rem;color:var(--navy-deep);font-weight:600">
            {{ normalBalancePreview || '— pick a type —' }}
          </div>
        </div>
        <div>
          <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Description</label>
          <input [(ngModel)]="newAccount.description" placeholder="Optional" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
        </div>
      </div>
      <div style="display:flex;gap:.75rem;margin-top:1.25rem">
        <button (click)="createAndSelect()" [disabled]="!newAccount.name || !newAccount.account_type || creatingAccount"
          style="flex:1;padding:.625rem;background:var(--navy-primary);color:#fff;border:none;border-radius:var(--radius-sm);cursor:pointer;font-weight:700;font-size:.875rem;font-family:var(--font-body)">
          {{ creatingAccount ? 'Creating…' : 'Create Account' }}
        </button>
        <button (click)="showModal = false" style="padding:.625rem 1rem;border:1.5px solid var(--border);background:var(--white);border-radius:var(--radius-sm);cursor:pointer;font-size:.875rem;font-family:var(--font-body)">Cancel</button>
      </div>
    </div>
  </div>
}
```

- [ ] **Step 3: Verify the app compiles**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```
Expected: `Build at: ... - Hash: ...` with no errors.

- [ ] **Step 4: Commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/shared/
git commit -m "feat: add AccountSelectComponent with searchable dropdown and inline quick-create modal"
```

---

## Task 2: Create `BankSelectComponent`

**Files:**
- Create: `frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.ts`
- Create: `frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.html`

Same pattern as `AccountSelectComponent` but for bank accounts. The quick-create modal embeds an `AccountSelectComponent` for the GL account field.

- [ ] **Step 1: Create the component TS file**

```typescript
// frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.ts
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
```

- [ ] **Step 2: Create the component HTML file**

```html
<!-- frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.html -->
<div style="position:relative">
  <input
    type="text"
    [(ngModel)]="searchText"
    (input)="onInput()"
    (focus)="showDropdown = true"
    [placeholder]="placeholder"
    autocomplete="off"
    style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box;background:var(--white)"
  />

  @if (showDropdown) {
    <div style="position:absolute;z-index:1000;top:100%;left:0;right:0;background:var(--white);border:1.5px solid var(--border);border-radius:var(--radius-sm);box-shadow:0 4px 16px rgba(0,0,0,.12);max-height:200px;overflow-y:auto;margin-top:2px">
      @for (bank of filteredBanks; track bank.bank_account_id) {
        <div
          (mousedown)="selectBank(bank)"
          style="padding:.5rem .75rem;cursor:pointer;font-size:.875rem;border-bottom:1px solid var(--border)"
          onmouseover="this.style.background='var(--navy-subtle)'"
          onmouseout="this.style.background=''"
        >
          {{ bank.name }}
          <span style="float:right;font-size:.75rem;color:var(--text-muted)">{{ bank.bank_name }}</span>
        </div>
      }
      @if (filteredBanks.length === 0) {
        <div style="padding:.5rem .75rem;font-size:.875rem;color:var(--text-muted);font-style:italic">No bank accounts match "{{ searchText }}"</div>
      }
      <div
        (mousedown)="openCreateModal()"
        style="padding:.5rem .75rem;cursor:pointer;font-size:.875rem;color:var(--navy-primary);font-weight:700;border-top:1.5px solid var(--border)"
        onmouseover="this.style.background='var(--navy-subtle)'"
        onmouseout="this.style.background=''"
      >
        + Create bank account…
      </div>
    </div>
  }
</div>

@if (showModal) {
  <div style="position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:2000;display:flex;align-items:center;justify-content:center" (click)="showModal = false">
    <div style="background:var(--white);border-radius:var(--radius-lg);padding:1.5rem;width:460px;max-width:95vw;box-shadow:0 8px 32px rgba(0,0,0,.18)" (click)="$event.stopPropagation()">
      <h3 style="margin:0 0 1.25rem;font-size:1.05rem;font-weight:700;color:var(--navy-deep)">New Bank Account</h3>
      @if (createError) {
        <p style="color:var(--danger);font-size:.85rem;margin:0 0 .75rem;padding:.5rem;background:rgba(239,68,68,.08);border-radius:var(--radius-sm)">{{ createError }}</p>
      }
      <div style="display:flex;flex-direction:column;gap:.75rem">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem">
          <div>
            <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Account Name *</label>
            <input [(ngModel)]="newBank.name" placeholder="e.g. GTBank Current" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
          </div>
          <div>
            <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Bank Name *</label>
            <input [(ngModel)]="newBank.bank_name" placeholder="e.g. GTBank" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem">
          <div>
            <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Account Number</label>
            <input [(ngModel)]="newBank.account_number" placeholder="0123456789" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:.875rem;box-sizing:border-box" />
          </div>
          <div>
            <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Opening Balance (₦)</label>
            <input [(ngModel)]="newBank.opening_balance" type="number" min="0" step="0.01" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:.875rem;box-sizing:border-box" />
          </div>
        </div>
        <div>
          <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">Opening Balance Date *</label>
          <input [(ngModel)]="newBank.opening_balance_date" type="date" style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
        </div>
        <div>
          <label style="display:block;font-size:.8rem;font-weight:600;color:var(--text-muted);margin-bottom:.25rem">GL Account (Cash/Bank)</label>
          <app-account-select
            [ngModel]="newBank.gl_account_id"
            (ngModelChange)="onGlAccountChange($event)"
            placeholder="Search GL account (optional)…"
          ></app-account-select>
        </div>
      </div>
      <div style="display:flex;gap:.75rem;margin-top:1.25rem">
        <button (click)="createAndSelect()" [disabled]="!newBank.name || !newBank.bank_name || !newBank.opening_balance_date || creatingBank"
          style="flex:1;padding:.625rem;background:var(--navy-primary);color:#fff;border:none;border-radius:var(--radius-sm);cursor:pointer;font-weight:700;font-size:.875rem;font-family:var(--font-body)">
          {{ creatingBank ? 'Creating…' : 'Create Bank Account' }}
        </button>
        <button (click)="showModal = false" style="padding:.625rem 1rem;border:1.5px solid var(--border);background:var(--white);border-radius:var(--radius-sm);cursor:pointer;font-size:.875rem;font-family:var(--font-body)">Cancel</button>
      </div>
    </div>
  </div>
}
```

- [ ] **Step 3: Verify the app compiles**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```
Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/shared/
git commit -m "feat: add BankSelectComponent with searchable dropdown and inline quick-create modal"
```

---

## Task 3: Restructure Shell Navigation — Add "Banking" Section

**Files:**
- Modify: `frontend/sage-frontend/src/app/shell/shell.component.ts`
- Modify: `frontend/sage-frontend/src/app/shell/shell.component.html`

Move Bank Accounts and Transactions out of "General Ledger" into a new "Banking" collapsible section. Rename "General Ledger" to "Ledger".

- [ ] **Step 1: Update `shell.component.ts`** — add `banking` key to `open` map

Replace the `open` property initialiser in `shell.component.ts`:

```typescript
open: Record<string, boolean> = {
  gl: true,
  banking: false,
  reports: false,
  payables: false,
  receivables: false,
  budget: false,
};
```

- [ ] **Step 2: Rewrite `shell.component.html`**

Replace the entire file content with:

```html
<div style="display:flex;height:100vh">
  <nav class="nav-sidebar">
    <!-- Brand -->
    <div class="nav-brand">
      <div class="nav-brand-wordmark">Sa<span>ge</span></div>
      <div class="nav-brand-sub">Topfaith University Finance</div>
    </div>

    <!-- Scrollable nav body -->
    <div class="nav-body">
      <a routerLink="/dashboard" routerLinkActive="active-link" [routerLinkActiveOptions]="{exact:true}"
         class="nav-link">Dashboard</a>

      <!-- Ledger -->
      <button class="nav-section-btn" (click)="toggle('gl')">
        Ledger
        <span class="nav-chevron" [style.transform]="open['gl'] ? 'rotate(90deg)' : 'rotate(0deg)'">&#9654;</span>
      </button>
      @if (open['gl']) {
        <a routerLink="/accounts" routerLinkActive="active-link" class="nav-child-link">Chart of Accounts</a>
        <a routerLink="/journals" routerLinkActive="active-link" class="nav-child-link">Journal Entries</a>
      }

      <!-- Banking -->
      <button class="nav-section-btn" (click)="toggle('banking')" style="margin-top:.25rem">
        Banking
        <span class="nav-chevron" [style.transform]="open['banking'] ? 'rotate(90deg)' : 'rotate(0deg)'">&#9654;</span>
      </button>
      @if (open['banking']) {
        <a routerLink="/banks" routerLinkActive="active-link" class="nav-child-link">Bank Accounts</a>
        <a routerLink="/banks/transactions" routerLinkActive="active-link" class="nav-child-link">Transactions</a>
      }

      <!-- Reports -->
      <button class="nav-section-btn" (click)="toggle('reports')">
        Reports
        <span class="nav-chevron" [style.transform]="open['reports'] ? 'rotate(90deg)' : 'rotate(0deg)'">&#9654;</span>
      </button>
      @if (open['reports']) {
        <a routerLink="/reports/trial-balance" routerLinkActive="active-link" class="nav-child-link">Trial Balance</a>
        <a routerLink="/reports/income-statement" routerLinkActive="active-link" class="nav-child-link">Income Statement</a>
        <a routerLink="/reports/balance-sheet" routerLinkActive="active-link" class="nav-child-link">Balance Sheet</a>
        <a routerLink="/reports/gl-detail" routerLinkActive="active-link" class="nav-child-link">GL Detail</a>
      }

      <!-- Payables -->
      <button class="nav-section-btn" (click)="toggle('payables')">
        Payables
        <span class="nav-chevron" [style.transform]="open['payables'] ? 'rotate(90deg)' : 'rotate(0deg)'">&#9654;</span>
      </button>
      @if (open['payables']) {
        <a routerLink="/payables/invoices" routerLinkActive="active-link" class="nav-child-link">AP Invoices</a>
        <a routerLink="/payables/vendors" routerLinkActive="active-link" class="nav-child-link">Vendors</a>
      }

      <!-- Receivables -->
      <button class="nav-section-btn" (click)="toggle('receivables')">
        Receivables
        <span class="nav-chevron" [style.transform]="open['receivables'] ? 'rotate(90deg)' : 'rotate(0deg)'">&#9654;</span>
      </button>
      @if (open['receivables']) {
        <a routerLink="/receivables/invoices" routerLinkActive="active-link" class="nav-child-link">AR Invoices</a>
        <a routerLink="/receivables/customers" routerLinkActive="active-link" class="nav-child-link">Customers</a>
      }

      <!-- Budget -->
      <button class="nav-section-btn" (click)="toggle('budget')">
        Budget
        <span class="nav-chevron" [style.transform]="open['budget'] ? 'rotate(90deg)' : 'rotate(0deg)'">&#9654;</span>
      </button>
      @if (open['budget']) {
        <a routerLink="/budget" routerLinkActive="active-link" class="nav-child-link">Budgets</a>
      }
    </div>

    <!-- Footer -->
    <div class="nav-footer">
      <button (click)="logout()" class="btn-secondary" style="width:100%">
        Sign Out
      </button>
    </div>
  </nav>

  <main class="main-content">
    <router-outlet></router-outlet>
  </main>
</div>
```

- [ ] **Step 3: Verify the app compiles**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/shell/
git commit -m "feat: add dedicated Banking section to sidebar nav, rename GL section to Ledger"
```

---

## Task 4: Redesign Journal Entry Form (Debit/Credit Columns)

**Files:**
- Modify: `frontend/sage-frontend/src/app/journals/entry-form/entry-form.component.ts`
- Modify: `frontend/sage-frontend/src/app/journals/entry-form/entry-form.component.html`

Replace `Account | Side | Amount | Memo` with `Account (AccountSelectComponent) | Debit (₦) | Credit (₦) | Memo`. On save, map `debit_amount > 0 → {side:'DEBIT', amount}`, `credit_amount > 0 → {side:'CREDIT', amount}`.

- [ ] **Step 1: Rewrite `entry-form.component.ts`**

```typescript
// frontend/sage-frontend/src/app/journals/entry-form/entry-form.component.ts
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { JournalsService } from '../../services/journals.service';
import { AccountsService } from '../../services/accounts.service';
import { AuthService } from '../../services/auth.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';

@Component({
  selector: 'app-entry-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AccountSelectComponent],
  templateUrl: './entry-form.component.html',
})
export class EntryFormComponent implements OnInit {
  form!: FormGroup;
  allAccounts: any[] = [];
  saving = false;
  posting = false;
  error = '';
  entryId: string | null = null;

  get isManagerOrAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Manager', 'Admin'].includes(r)) ?? false;
  }

  get isEditMode(): boolean { return !!this.entryId; }
  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get totalDebit(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.debit_amount) || 0), 0);
  }

  get totalCredit(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.credit_amount) || 0), 0);
  }

  get isBalanced(): boolean {
    return this.lines.length >= 2 && Math.abs(this.totalDebit - this.totalCredit) < 0.005;
  }

  constructor(
    private fb: FormBuilder,
    private journalsService: JournalsService,
    private accountsService: AccountsService,
    private auth: AuthService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      description: ['', Validators.required],
      entry_type: ['MANUAL'],
      lines: this.fb.array([]),
    });
    try {
      const data = await this.accountsService.getAll();
      this.allAccounts = data.results ?? data;
      this.entryId = this.route.snapshot.paramMap.get('id');
      if (this.entryId) {
        const entry = await this.journalsService.getEntry(this.entryId);
        this.form.patchValue({ date: entry.date ?? '', description: entry.description ?? '', entry_type: entry.entry_type ?? 'MANUAL' });
        this.lines.clear();
        for (const line of (entry.lines ?? [])) {
          this.lines.push(this.fb.group({
            account_id: [line.account_id ?? '', Validators.required],
            debit_amount: [line.side === 'DEBIT' ? line.amount : null],
            credit_amount: [line.side === 'CREDIT' ? line.amount : null],
            description: [line.description ?? ''],
          }));
        }
      }
      if (this.lines.length === 0) {
        this.addLine('DEBIT');
        this.addLine('CREDIT');
      }
    } catch {
      this.error = 'Failed to load journal entry form. Please refresh.';
    }
  }

  addLine(side: 'DEBIT' | 'CREDIT' = 'DEBIT') {
    this.lines.push(this.fb.group({
      account_id: ['', Validators.required],
      debit_amount: [side === 'DEBIT' ? null : null],
      credit_amount: [side === 'CREDIT' ? null : null],
      description: [''],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 2) this.lines.removeAt(i);
  }

  onAccountChange(i: number, id: string) {
    this.lines.at(i).patchValue({ account_id: id });
  }

  private buildPayload() {
    const val = this.form.value;
    return {
      date: val.date,
      description: val.description,
      entry_type: val.entry_type,
      lines: val.lines
        .filter((l: any) => Number(l.debit_amount) > 0 || Number(l.credit_amount) > 0)
        .map((l: any) => ({
          account_id: l.account_id,
          side: Number(l.debit_amount) > 0 ? 'DEBIT' : 'CREDIT',
          amount: Number(l.debit_amount) > 0 ? Number(l.debit_amount) : Number(l.credit_amount),
          description: l.description,
        })),
    };
  }

  async save() {
    if (!this.form.valid || !this.isBalanced) return;
    this.saving = true;
    this.error = '';
    try {
      const entry = this.entryId
        ? await this.journalsService.updateEntry(this.entryId, this.buildPayload())
        : await this.journalsService.createEntry(this.buildPayload());
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }

  async saveAndPost() {
    if (!this.form.valid || !this.isBalanced) return;
    this.posting = true;
    this.error = '';
    try {
      const entry = this.entryId
        ? await this.journalsService.updateEntry(this.entryId, this.buildPayload())
        : await this.journalsService.createEntry(this.buildPayload());
      await this.journalsService.postEntry(entry.entry_id);
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Post failed.');
    } finally { this.posting = false; }
  }
}
```

- [ ] **Step 2: Rewrite `entry-form.component.html`**

```html
<div style="max-width:960px">
  <h2 style="margin:0 0 1.5rem;font-family:var(--font-serif);color:var(--navy-deep)">{{ isEditMode ? 'Edit Journal Entry' : 'New Journal Entry' }}</h2>
  @if (error) { <p style="color:var(--danger);margin-bottom:1rem;font-size:.875rem">{{ error }}</p> }

  <form [formGroup]="form">
    <!-- Header fields -->
    <div class="card" style="padding:1.25rem;margin-bottom:1rem">
      <div style="display:grid;grid-template-columns:1fr 2fr;gap:1rem">
        <div>
          <label style="display:block;font-size:.8rem;font-weight:700;color:var(--text-muted);margin-bottom:.3rem">Date *</label>
          <input formControlName="date" type="date"
            style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
        </div>
        <div>
          <label style="display:block;font-size:.8rem;font-weight:700;color:var(--text-muted);margin-bottom:.3rem">Description *</label>
          <input formControlName="description" placeholder="Entry description"
            style="width:100%;padding:.5rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
        </div>
      </div>
    </div>

    <!-- Lines table -->
    <div class="card" style="margin-bottom:1rem;overflow:hidden">
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:var(--navy-subtle)">
          <tr>
            <th style="text-align:left;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep)">Account</th>
            <th style="text-align:right;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep);width:150px">Debit (₦)</th>
            <th style="text-align:right;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep);width:150px">Credit (₦)</th>
            <th style="text-align:left;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep)">Memo</th>
            <th style="width:40px"></th>
          </tr>
        </thead>
        <tbody formArrayName="lines">
          @for (line of lines.controls; track $index) {
            <tr [formGroupName]="$index" style="border-top:1px solid var(--border)">
              <td style="padding:.5rem 1rem">
                <app-account-select
                  [formControlName]="'account_id'"
                  [allAccounts]="allAccounts"
                  (accountsChanged)="allAccounts = $event"
                  placeholder="Search account…"
                ></app-account-select>
              </td>
              <td style="padding:.5rem 1rem">
                <input formControlName="debit_amount" type="number" min="0.01" step="0.01" placeholder="0.00"
                  style="width:100%;padding:.4rem .5rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-mono);font-size:.875rem;text-align:right;box-sizing:border-box" />
              </td>
              <td style="padding:.5rem 1rem">
                <input formControlName="credit_amount" type="number" min="0.01" step="0.01" placeholder="0.00"
                  style="width:100%;padding:.4rem .5rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-mono);font-size:.875rem;text-align:right;box-sizing:border-box" />
              </td>
              <td style="padding:.5rem 1rem">
                <input formControlName="description" placeholder="optional"
                  style="width:100%;padding:.4rem .5rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
              </td>
              <td style="padding:.5rem;text-align:center">
                <button type="button" (click)="removeLine($index)" [disabled]="lines.length <= 2"
                  [style.opacity]="lines.length <= 2 ? '0.3' : '1'"
                  style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:1rem;line-height:1">✕</button>
              </td>
            </tr>
          }
        </tbody>
      </table>

      <div style="display:flex;justify-content:space-between;align-items:center;padding:.75rem 1rem;background:var(--navy-subtle);border-top:1px solid var(--border)">
        <button type="button" (click)="addLine()"
          style="background:none;border:1.5px dashed var(--border-strong);padding:.375rem .875rem;border-radius:var(--radius-sm);cursor:pointer;color:var(--text-secondary);font-size:.875rem;font-family:var(--font-body)">
          + Add line
        </button>
        <div style="display:flex;gap:2rem;font-size:.9rem;font-family:var(--font-mono)">
          <span>Debit: <strong>₦{{ totalDebit | number:'1.2-2' }}</strong></span>
          <span>Credit: <strong>₦{{ totalCredit | number:'1.2-2' }}</strong></span>
          <span [style.color]="isBalanced ? '#10b981' : 'var(--danger)'" style="font-weight:700">
            {{ isBalanced ? '✓ Balanced' : '✗ Unbalanced' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div style="display:flex;gap:.75rem">
      <button type="button" (click)="save()" [disabled]="!form.valid || !isBalanced || saving"
        class="btn-secondary" style="padding:.625rem 1.25rem">
        {{ saving ? 'Saving…' : (isEditMode ? 'Save Changes' : 'Save as Draft') }}
      </button>
      @if (isManagerOrAdmin) {
        <button type="button" (click)="saveAndPost()" [disabled]="!form.valid || !isBalanced || posting"
          class="btn-primary" style="padding:.625rem 1.25rem">
          {{ posting ? 'Posting…' : 'Save & Post' }}
        </button>
      }
    </div>
  </form>
</div>
```

Note: `AccountSelectComponent` implements `ControlValueAccessor`, so `[formControlName]="'account_id'"` wires directly into the `FormGroup` at each line index.

- [ ] **Step 3: Verify the app compiles**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/journals/entry-form/
git commit -m "feat: redesign journal entry form with Debit/Credit columns and AccountSelectComponent"
```

---

## Task 5: Integrate Smart Selectors — Bank Transaction Form

**Files:**
- Modify: `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.ts`
- Modify: `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.html`

Replace both bank account `<select>` dropdowns with `BankSelectComponent` and the splits account `<select>` with `AccountSelectComponent`.

- [ ] **Step 1: Update `bank-transaction-form.component.ts`**

Replace the entire file:

```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { BankTransactionsService } from '../../services/bank-transactions.service';
import { BanksService } from '../../services/banks.service';
import { AccountsService } from '../../services/accounts.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';

@Component({
  selector: 'app-bank-transaction-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterModule, AccountSelectComponent, BankSelectComponent],
  templateUrl: './bank-transaction-form.component.html',
})
export class BankTransactionFormComponent implements OnInit {
  form!: FormGroup;
  allBanks: any[] = [];
  allAccounts: any[] = [];
  saving = false;
  error = '';

  get splits(): FormArray { return this.form.get('splits') as FormArray; }
  get transactionType(): string { return this.form.get('transaction_type')?.value ?? ''; }
  get sourceBankId(): string { return this.form.get('source_bank_id')?.value ?? ''; }
  get totalSplits(): number {
    return this.splits.controls.reduce((sum, c) => sum + (Number(c.value.amount) || 0), 0);
  }

  constructor(
    private fb: FormBuilder,
    private route: ActivatedRoute,
    private router: Router,
    private txnService: BankTransactionsService,
    private banksService: BanksService,
    private accountsService: AccountsService,
  ) {}

  async ngOnInit() {
    const preBankId = this.route.snapshot.queryParamMap.get('bank_id') ?? '';
    this.form = this.fb.group({
      transaction_type: ['RECEIPT', Validators.required],
      source_bank_id: [preBankId, Validators.required],
      destination_bank_id: [''],
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      description: [''],
      transfer_amount: [null],
      splits: this.fb.array([]),
    });
    this.addSplit();
    try {
      const [banks, accounts] = await Promise.all([
        this.banksService.getAccounts(),
        this.accountsService.getAll(),
      ]);
      this.allBanks = banks.results ?? banks;
      this.allAccounts = accounts.results ?? accounts;
    } catch {
      this.error = 'Failed to load reference data.';
    }
  }

  addSplit() {
    this.splits.push(this.fb.group({
      account_id: ['', Validators.required],
      amount: [null, [Validators.required, Validators.min(0.01)]],
      description: [''],
    }));
  }

  changeType(type: string) {
    this.form.get('transaction_type')!.setValue(type);
    if (type === 'TRANSFER') {
      while (this.splits.length > 0) this.splits.removeAt(0);
    } else if (this.splits.length === 0) {
      this.addSplit();
    }
  }

  removeSplit(i: number) {
    if (this.splits.length > 1) this.splits.removeAt(i);
  }

  async submit() {
    if (this.form.invalid) return;
    const val = this.form.value;
    if (val.transaction_type === 'TRANSFER') {
      if (!val.destination_bank_id) { this.error = 'Please select a destination bank account.'; return; }
      if (!val.transfer_amount || Number(val.transfer_amount) <= 0) { this.error = 'Please enter a transfer amount greater than 0.'; return; }
    }
    this.saving = true;
    this.error = '';
    const payload: any = {
      transaction_type: val.transaction_type,
      date: val.date,
      description: val.description,
      source_bank_id: val.source_bank_id,
    };
    if (val.transaction_type === 'TRANSFER') {
      payload.destination_bank_id = val.destination_bank_id;
      payload.transfer_amount = Number(val.transfer_amount);
    } else {
      payload.splits = val.splits.map((s: any) => ({
        account_id: s.account_id,
        amount: Number(s.amount),
        description: s.description,
      }));
    }
    try {
      await this.txnService.create(payload);
      this.router.navigate(['/banks', val.source_bank_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Failed to save transaction.';
    } finally {
      this.saving = false;
    }
  }
}
```

- [ ] **Step 2: Rewrite `bank-transaction-form.component.html`**

```html
<div style="max-width:820px">
  <h1 class="page-title" style="margin-bottom:1.5rem">New Bank Transaction</h1>

  @if (error) {
    <p style="color:var(--danger);margin-bottom:1rem;font-size:.875rem">{{ error }}</p>
  }

  <form [formGroup]="form">
    <!-- Type selector -->
    <div class="card" style="padding:1.25rem;margin-bottom:1rem">
      <p style="font-size:.75rem;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);margin-bottom:.75rem">Transaction Type</p>
      <div style="display:flex;gap:.5rem">
        @for (type of ['RECEIPT','PAYMENT','TRANSFER']; track type) {
          <button type="button" (click)="changeType(type)"
            [style.background]="transactionType === type ? 'var(--navy-primary)' : 'var(--white)'"
            [style.color]="transactionType === type ? '#fff' : 'var(--text-secondary)'"
            [style.borderColor]="transactionType === type ? 'var(--navy-primary)' : 'var(--border)'"
            style="padding:.5rem 1.25rem;border:1.5px solid;border-radius:var(--radius-sm);cursor:pointer;font-weight:700;font-size:.875rem;font-family:var(--font-body);transition:all 150ms">
            {{ type }}
          </button>
        }
      </div>
    </div>

    <!-- Header fields -->
    <div class="card" style="padding:1.25rem;margin-bottom:1rem">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem">
        <div>
          <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Source Bank Account *</label>
          <app-bank-select
            formControlName="source_bank_id"
            [allBanks]="allBanks"
            (banksChanged)="allBanks = $event"
            placeholder="Search or create bank account…"
          ></app-bank-select>
        </div>

        @if (transactionType === 'TRANSFER') {
          <div>
            <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Destination Bank Account *</label>
            <app-bank-select
              formControlName="destination_bank_id"
              [allBanks]="allBanks"
              [excludeId]="sourceBankId"
              (banksChanged)="allBanks = $event"
              placeholder="Search or create bank account…"
            ></app-bank-select>
          </div>
        }
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
        <div>
          <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Date *</label>
          <input formControlName="date" type="date"
            style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
        </div>
        <div>
          <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Description</label>
          <input formControlName="description" placeholder="e.g. Utility payment"
            style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
        </div>
      </div>
    </div>

    @if (transactionType === 'TRANSFER') {
      <div class="card" style="padding:1.25rem;margin-bottom:1rem">
        <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Amount (₦) *</label>
        <input formControlName="transfer_amount" type="number" min="0.01" step="0.01" placeholder="0.00"
          style="width:240px;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:.875rem;text-align:right;box-sizing:border-box" />
      </div>
    }

    @if (transactionType !== 'TRANSFER') {
      <div class="card" style="margin-bottom:1rem;overflow:hidden">
        <table style="width:100%;border-collapse:collapse">
          <thead style="background:var(--navy-subtle)">
            <tr>
              <th style="text-align:left;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep)">Contra Account</th>
              <th style="text-align:right;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep);width:160px">Amount (₦)</th>
              <th style="text-align:left;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep)">Memo</th>
              <th style="width:36px"></th>
            </tr>
          </thead>
          <tbody formArrayName="splits">
            @for (split of splits.controls; track $index) {
              <tr [formGroupName]="$index" style="border-top:1px solid var(--border)">
                <td style="padding:.5rem 1rem">
                  <app-account-select
                    formControlName="account_id"
                    [allAccounts]="allAccounts"
                    (accountsChanged)="allAccounts = $event"
                    placeholder="Search account…"
                  ></app-account-select>
                </td>
                <td style="padding:.5rem 1rem">
                  <input formControlName="amount" type="number" min="0.01" step="0.01" placeholder="0.00"
                    style="width:100%;padding:.4rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-mono);font-size:.875rem;text-align:right;box-sizing:border-box" />
                </td>
                <td style="padding:.5rem 1rem">
                  <input formControlName="description" placeholder="optional"
                    style="width:100%;padding:.4rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-body);font-size:.84rem;box-sizing:border-box" />
                </td>
                <td style="padding:.5rem;text-align:center">
                  <button type="button" (click)="removeSplit($index)"
                    [disabled]="splits.length === 1"
                    [style.opacity]="splits.length === 1 ? '0.3' : '1'"
                    style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:1rem;line-height:1">✕</button>
                </td>
              </tr>
            }
          </tbody>
        </table>
        <div style="display:flex;justify-content:space-between;align-items:center;padding:.75rem 1rem;background:var(--navy-subtle);border-top:1px solid var(--border)">
          <button type="button" (click)="addSplit()"
            style="background:none;border:1.5px dashed var(--border-strong);padding:.375rem .875rem;border-radius:var(--radius-sm);cursor:pointer;color:var(--text-secondary);font-size:.875rem;font-family:var(--font-body)">
            + Add split
          </button>
          <span class="mono" style="font-size:.9rem;color:var(--text-secondary)">
            Total: <strong>₦{{ totalSplits | number:'1.2-2' }}</strong>
          </span>
        </div>
      </div>
    }

    <div style="display:flex;gap:.75rem">
      <button type="button" (click)="submit()" [disabled]="form.invalid || saving" class="btn-primary">
        {{ saving ? 'Posting…' : 'Post Transaction' }}
      </button>
      <a routerLink="/banks/transactions" class="btn-secondary">Cancel</a>
    </div>
  </form>
</div>
```

- [ ] **Step 3: Build check**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/banks/bank-transaction-form/
git commit -m "feat: use AccountSelectComponent and BankSelectComponent in bank transaction form"
```

---

## Task 6: Integrate Smart Selectors — Payables Invoice Form

**Files:**
- Modify: `frontend/sage-frontend/src/app/payables/invoice-form/invoice-form.component.ts`
- Modify: `frontend/sage-frontend/src/app/payables/invoice-form/invoice-form.component.html`

Replace AP account `<select>` and expense account line `<select>` with `AccountSelectComponent`. Also normalise inline styles to CSS variables.

- [ ] **Step 1: Update `invoice-form.component.ts` imports**

Read the current file at `frontend/sage-frontend/src/app/payables/invoice-form/invoice-form.component.ts`, then add `AccountSelectComponent` to the `imports` array:

```typescript
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
```

Add to the component's `imports` array: `AccountSelectComponent`

Also add `allAccounts: any[] = [];` as a property and in `ngOnInit` assign:
```typescript
this.allAccounts = data.results ?? data;  // same as existing accounts load
```

Replace `accounts: any[] = [];` with `accounts: any[] = []; allAccounts: any[] = [];` and after `this.accounts = data.results ?? data;` add `this.allAccounts = [...this.accounts];`.

- [ ] **Step 2: Replace AP account `<select>` in `invoice-form.component.html`**

Find:
```html
        <div>
          <label style="display:block;font-size:.8rem;color:#555;margin-bottom:.25rem">AP Account *</label>
          <select formControlName="ap_account_id"
            style="width:100%;padding:.5rem;border:1px solid #ccc;border-radius:4px">
            <option value="">— select account —</option>
            @for (a of accounts; track a.account_id) {
              <option [value]="a.account_id">{{ a.code }} — {{ a.name }}</option>
            }
          </select>
        </div>
```

Replace with:
```html
        <div>
          <label style="display:block;font-size:.8rem;font-weight:700;color:var(--text-muted);margin-bottom:.3rem">AP Account *</label>
          <app-account-select
            formControlName="ap_account_id"
            [allAccounts]="allAccounts"
            (accountsChanged)="allAccounts = $event"
            placeholder="Search AP account…"
          ></app-account-select>
        </div>
```

- [ ] **Step 3: Replace expense account `<select>` in each line row**

Find:
```html
              <td style="padding:.5rem 1rem">
                <select formControlName="expense_account_id"
                  style="width:100%;padding:.375rem;border:1px solid #ccc;border-radius:4px">
                  <option value="">— select —</option>
                  @for (a of accounts; track a.account_id) {
                    <option [value]="a.account_id">{{ a.code }} — {{ a.name }}</option>
                  }
                </select>
              </td>
```

Replace with:
```html
              <td style="padding:.5rem 1rem">
                <app-account-select
                  formControlName="expense_account_id"
                  [allAccounts]="allAccounts"
                  (accountsChanged)="allAccounts = $event"
                  placeholder="Search expense account…"
                ></app-account-select>
              </td>
```

- [ ] **Step 4: Build check and commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/payables/invoice-form/
git commit -m "feat: use AccountSelectComponent in payables invoice form"
```

---

## Task 7: Integrate Smart Selectors — Receivables Invoice Form

**Files:**
- Modify: `frontend/sage-frontend/src/app/receivables/invoice-form/invoice-form.component.ts`
- Modify: `frontend/sage-frontend/src/app/receivables/invoice-form/invoice-form.component.html`

Same as Task 6 but for AR account + revenue account lines.

- [ ] **Step 1: Update `receivables/invoice-form/invoice-form.component.ts`** — same pattern as Task 6: import `AccountSelectComponent`, add to `imports` array, add `allAccounts: any[] = []`, assign after accounts load.

- [ ] **Step 2: Replace AR account `<select>` in `receivables/invoice-form/invoice-form.component.html`**

Find:
```html
        <div>
          <label style="display:block;font-size:.8rem;color:#555;margin-bottom:.25rem">AR Account *</label>
          <select formControlName="ar_account_id"
            style="width:100%;padding:.5rem;border:1px solid #ccc;border-radius:4px">
            <option value="">— select account —</option>
            @for (a of accounts; track a.account_id) {
              <option [value]="a.account_id">{{ a.code }} — {{ a.name }}</option>
            }
          </select>
        </div>
```

Replace with:
```html
        <div>
          <label style="display:block;font-size:.8rem;font-weight:700;color:var(--text-muted);margin-bottom:.3rem">AR Account *</label>
          <app-account-select
            formControlName="ar_account_id"
            [allAccounts]="allAccounts"
            (accountsChanged)="allAccounts = $event"
            placeholder="Search AR account…"
          ></app-account-select>
        </div>
```

- [ ] **Step 3: Replace revenue account `<select>` in each line row**

Find:
```html
              <td style="padding:.5rem 1rem">
                <select formControlName="revenue_account_id"
                  style="width:100%;padding:.375rem;border:1px solid #ccc;border-radius:4px">
                  <option value="">— select —</option>
                  @for (a of accounts; track a.account_id) {
                    <option [value]="a.account_id">{{ a.code }} — {{ a.name }}</option>
                  }
                </select>
              </td>
```

Replace with:
```html
              <td style="padding:.5rem 1rem">
                <app-account-select
                  formControlName="revenue_account_id"
                  [allAccounts]="allAccounts"
                  (accountsChanged)="allAccounts = $event"
                  placeholder="Search revenue account…"
                ></app-account-select>
              </td>
```

- [ ] **Step 4: Build check and commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/receivables/invoice-form/
git commit -m "feat: use AccountSelectComponent in receivables invoice form"
```

---

## Task 8: Integrate Smart Selector — Bank Account GL Field

**Files:**
- Modify: `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.html`
- Modify: `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.ts`

Replace the GL account `<select>` inside the bank account create/edit form with `AccountSelectComponent`.

- [ ] **Step 1: Read the current `bank-account-list.component.ts`**

Read: `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.ts`

Add import:
```typescript
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
```

Add `AccountSelectComponent` to the `imports` array.

Add a property `allAccounts: any[] = [];` and load it in `ngOnInit` alongside the bank accounts:
```typescript
const [accounts, banks] = await Promise.all([
  this.accountsService.getAll(),
  this.banksService.getAccounts(),
]);
this.allAccounts = (accounts.results ?? accounts);
this.accounts = banks.results ?? banks;
```

Add a method:
```typescript
onGlAccountChange(id: string) {
  this.form.gl_account_id_input = id;
}
```

- [ ] **Step 2: Replace GL account `<select>` in `bank-account-list.component.html`**

Find:
```html
          <div class="form-full">
            <label style="display:block;font-size:0.85rem;color:var(--charcoal-light);margin-bottom:0.25rem;font-weight:500;">GL Account (Cash/Bank)</label>
            <select [(ngModel)]="form.gl_account_id_input"
              style="width:100%;padding:0.75rem;border:1px solid var(--gray-light);border-radius:var(--radius-sm);box-sizing:border-box;font-family:var(--font-sans);">
              <option value="">— none —</option>
              @for (acct of glAccounts; track acct.account_id) {
                <option [value]="acct.account_id">{{ acct.code }} — {{ acct.name }}</option>
              }
            </select>
          </div>
```

Replace with:
```html
          <div class="form-full">
            <label style="display:block;font-size:0.85rem;color:var(--charcoal-light);margin-bottom:0.25rem;font-weight:500;">GL Account (Cash/Bank)</label>
            <app-account-select
              [ngModel]="form.gl_account_id_input"
              (ngModelChange)="onGlAccountChange($event)"
              [allAccounts]="allAccounts"
              (accountsChanged)="allAccounts = $event"
              placeholder="Search GL account (optional)…"
            ></app-account-select>
          </div>
```

- [ ] **Step 3: Build check and commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/banks/bank-account-list/
git commit -m "feat: use AccountSelectComponent for GL account field in bank account form"
```

---

## Task 9: SageOne Alignment Sweep — Confirm Dialogs on Delete

**Files:**
- Modify: `frontend/sage-frontend/src/app/accounts/account-list/account-list.component.html`
- Modify: `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.html`
- Modify: `frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.html`
- Modify: `frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.html`
- Modify: `frontend/sage-frontend/src/app/payables/invoice-list/invoice-list.component.html`
- Modify: `frontend/sage-frontend/src/app/receivables/invoice-list/invoice-list.component.html`

All Delete buttons need a `window.confirm()` guard. The pattern is the same for each file.

- [ ] **Step 1: Check the current TS delete methods in account-list, vendor-list, customer-list**

Read each `.component.ts` to confirm the delete method name. They will be something like `deleteAccount(acct)`, `deleteVendor(vendor)`, `deleteCustomer(customer)`. The guard goes inside the method, not the template.

In `account-list.component.ts`, find `deleteAccount` and prepend:
```typescript
if (!window.confirm(`Delete account "${account.name}"? This cannot be undone.`)) return;
```

In `vendor-list.component.ts`, find `deleteVendor` and prepend:
```typescript
if (!window.confirm(`Delete vendor "${vendor.name}"? This cannot be undone.`)) return;
```

In `customer-list.component.ts`, find `deleteCustomer` and prepend:
```typescript
if (!window.confirm(`Delete customer "${customer.name}"? This cannot be undone.`)) return;
```

In `bank-account-list.component.ts`, find `deleteAccount` and prepend:
```typescript
if (!window.confirm(`Delete bank account "${account.name}"? This cannot be undone.`)) return;
```

- [ ] **Step 2: Check invoice-list delete methods for payables and receivables**

Read `payables/invoice-list/invoice-list.component.ts` and `receivables/invoice-list/invoice-list.component.ts`. Find the delete method in each and prepend:
```typescript
if (!window.confirm('Delete this invoice? This cannot be undone.')) return;
```

- [ ] **Step 3: Build check and commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/accounts/account-list/ frontend/sage-frontend/src/app/banks/bank-account-list/ frontend/sage-frontend/src/app/payables/ frontend/sage-frontend/src/app/receivables/
git commit -m "feat: add confirmation dialogs to all delete actions"
```

---

## Task 10: SageOne Alignment Sweep — Empty States, Status Badges, Style Normalisation

**Files:**
- Modify: `frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.html`
- Modify: `frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.html`
- Modify: `frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.html`
- Modify: `frontend/sage-frontend/src/app/payables/invoice-list/invoice-list.component.html`
- Modify: `frontend/sage-frontend/src/app/receivables/invoice-list/invoice-list.component.html`

- [ ] **Step 1: Read current vendor-list and customer-list HTML**

For `vendor-list.component.html`, find:
```html
        <tr><td colspan="4" style="padding:1rem;text-align:center;color:#888">No vendors yet.</td></tr>
```
Replace with:
```html
        <tr>
          <td colspan="4" style="padding:2.5rem;text-align:center;color:var(--text-muted)">
            No vendors yet.
            <br><br>
            <button (click)="showForm = true" class="btn-primary" style="padding:.5rem 1.25rem;font-size:.875rem">+ Add first vendor</button>
          </td>
        </tr>
```

For `customer-list.component.html`, apply the same pattern:
```html
        <tr>
          <td colspan="4" style="padding:2.5rem;text-align:center;color:var(--text-muted)">
            No customers yet.
            <br><br>
            <button (click)="showForm = true" class="btn-primary" style="padding:.5rem 1.25rem;font-size:.875rem">+ Add first customer</button>
          </td>
        </tr>
```

- [ ] **Step 2: Read and update invoice-list empty states**

Read `payables/invoice-list/invoice-list.component.html`. Find the `@empty` block or empty-row `td` and replace with:
```html
        <tr>
          <td [attr.colspan]="6" style="padding:2.5rem;text-align:center;color:var(--text-muted)">
            No purchase invoices yet.
            <br><br>
            <a routerLink="/payables/invoices/new" class="btn-primary" style="padding:.5rem 1.25rem;font-size:.875rem;text-decoration:none">+ Create first invoice</a>
          </td>
        </tr>
```

For `receivables/invoice-list/invoice-list.component.html`:
```html
        <tr>
          <td [attr.colspan]="6" style="padding:2.5rem;text-align:center;color:var(--text-muted)">
            No sales invoices yet.
            <br><br>
            <a routerLink="/receivables/invoices/new" class="btn-primary" style="padding:.5rem 1.25rem;font-size:.875rem;text-decoration:none">+ Create first invoice</a>
          </td>
        </tr>
```

- [ ] **Step 3: Verify AP/AR invoice-list pages have status badges**

Read `payables/invoice-list/invoice-list.component.html` and `receivables/invoice-list/invoice-list.component.html`. Check if there is a status column. If the `status` field is shown as plain text, wrap it in a badge span. Pattern to use wherever `invoice.status` or `entry.status` is displayed as bare text:

For DRAFT/POSTED/PAID status, use:
```html
<span [ngStyle]="statusBadgeStyle(invoice.status)">{{ invoice.status }}</span>
```

Add `statusBadgeStyle` method to the component TS:
```typescript
statusBadgeStyle(status: string): Record<string, string> {
  const map: Record<string, Record<string, string>> = {
    DRAFT:  { background: '#F3F4F6', color: '#6B7280' },
    POSTED: { background: '#EFF6FF', color: '#1D4ED8' },
    PAID:   { background: '#F0FDF4', color: '#15803D' },
    VOID:   { background: '#FFF1F2', color: '#B91C1C' },
  };
  return {
    ...(map[status] ?? map['DRAFT']),
    display: 'inline-block', padding: '.15rem .5rem',
    borderRadius: '4px', fontSize: '.75rem', fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: '.04em',
  };
}
```

- [ ] **Step 4: Final build check and commit**

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records/frontend/sage-frontend"
npx ng build --configuration development 2>&1 | tail -20
```

```bash
cd "/Users/etimbukabraham/Dropbox/Topfaith/University/UNiversity Apps/accounting_records"
git add frontend/sage-frontend/src/app/
git commit -m "feat: SageOne alignment — empty states with CTAs, status badges on AP/AR invoice lists"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|------------------|------|
| Smart account selector component | Task 1 |
| Inline account quick-create modal | Task 1 |
| Smart bank account selector component | Task 2 |
| Inline bank account quick-create modal | Task 2 |
| Banking sidebar section (separate from Ledger) | Task 3 |
| Journal entry: Debit/Credit columns instead of Side dropdown | Task 4 |
| Journal entry: AccountSelectComponent in lines | Task 4 |
| Bank transaction form: BankSelectComponent + AccountSelectComponent | Task 5 |
| Payables invoice: AccountSelectComponent for AP + expense accounts | Task 6 |
| Receivables invoice: AccountSelectComponent for AR + revenue accounts | Task 7 |
| Bank account create form: AccountSelectComponent for GL field | Task 8 |
| Confirm dialogs on all Delete buttons | Task 9 |
| Empty-state messages with CTA | Task 10 |
| Status badges on AP/AR invoice lists | Task 10 |
