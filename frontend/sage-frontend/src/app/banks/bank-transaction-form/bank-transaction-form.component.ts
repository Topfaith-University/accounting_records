import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { BankTransactionsService } from '../../services/bank-transactions.service';
import { BanksService } from '../../services/banks.service';
import { AccountsService } from '../../services/accounts.service';
import { PayablesService } from '../../services/payables.service';
import { ReceivablesService } from '../../services/receivables.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';
import { VendorSelectComponent } from '../../shared/vendor-select/vendor-select.component';
import { CustomerSelectComponent } from '../../shared/customer-select/customer-select.component';

@Component({
  selector: 'app-bank-transaction-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterModule,
            AccountSelectComponent, BankSelectComponent,
            VendorSelectComponent, CustomerSelectComponent],
  templateUrl: './bank-transaction-form.component.html',
})
export class BankTransactionFormComponent implements OnInit {
  allBanks: any[] = [];
  allAccounts: any[] = [];
  allVendors: any[] = [];
  allCustomers: any[] = [];
  form!: FormGroup;
  saving = false;
  saveError = '';
  saveResults: { ok: boolean; msg: string }[] = [];

  // Open (POSTED, unpaid) invoices for the party selected on each row, keyed by row index.
  rowOpenInvoices: any[][] = [];

  get rows(): FormArray { return this.form.get('rows') as FormArray; }
  get sourceBankId(): string { return this.form.get('source_bank_id')?.value ?? ''; }

  constructor(
    private fb: FormBuilder,
    private route: ActivatedRoute,
    private router: Router,
    private txnService: BankTransactionsService,
    private banksService: BanksService,
    private accountsService: AccountsService,
    private payablesService: PayablesService,
    private receivablesService: ReceivablesService,
  ) {}

  async ngOnInit() {
    const preBankId = this.route.snapshot.queryParamMap.get('bank_id') ?? '';
    this.form = this.fb.group({
      source_bank_id: [preBankId, Validators.required],
      rows: this.fb.array([]),
    });
    this.addRow();

    try {
      const [banks, accounts, vendors, customers] = await Promise.all([
        this.banksService.getAccounts(),
        this.accountsService.getAll(),
        this.payablesService.getVendors(),
        this.receivablesService.getCustomers(),
      ]);
      this.allBanks = banks.results ?? banks;
      this.allAccounts = accounts.results ?? accounts;
      this.allVendors = vendors.results ?? vendors;
      this.allCustomers = customers.results ?? customers;
    } catch {
      this.saveError = 'Failed to load reference data.';
    }
  }

  get otherBanks(): any[] {
    return this.allBanks.filter(b => b.bank_account_id !== this.sourceBankId);
  }

  rowGroup(i: number): FormGroup {
    return this.rows.at(i) as FormGroup;
  }

  rowType(i: number): string {
    return this.rowGroup(i).get('type')?.value ?? 'LEDGER';
  }

  addRow() {
    const group = this.fb.group({
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      description: [''],
      type: ['LEDGER', Validators.required],
      account_id: [''],
      bank_account_id: [''],
      vendor_id: [''],
      customer_id: [''],
      contra_account_id: [''],
      reference: [''],
      spent: [null],
      received: [null],
      selected_invoice_id: [''],
    });
    this.rows.push(group);
    this.rowOpenInvoices.push([]);

    group.get('vendor_id')!.valueChanges.subscribe(vendorId => this.onVendorChange(group, vendorId));
    group.get('customer_id')!.valueChanges.subscribe(customerId => this.onCustomerChange(group, customerId));
  }

  removeRow(i: number) {
    if (this.rows.length > 1) {
      this.rows.removeAt(i);
      this.rowOpenInvoices.splice(i, 1);
    }
  }

  onTypeChange(i: number) {
    const g = this.rowGroup(i);
    g.patchValue({ account_id: '', bank_account_id: '', vendor_id: '', customer_id: '', contra_account_id: '', selected_invoice_id: '' });
    this.rowOpenInvoices[i] = [];
  }

  private rowIndexOf(group: FormGroup): number {
    return this.rows.controls.indexOf(group);
  }

  async onVendorChange(group: FormGroup, vendorId: string | null) {
    group.patchValue({ selected_invoice_id: '' }, { emitEvent: false });
    const idx = this.rowIndexOf(group);
    if (idx === -1) return;
    if (!vendorId) { this.rowOpenInvoices[idx] = []; return; }
    try {
      const res = await this.payablesService.getInvoices({ vendor_id: vendorId, status: 'POSTED' });
      this.rowOpenInvoices[idx] = res.results ?? res;
    } catch {
      this.rowOpenInvoices[idx] = [];
    }
  }

  async onCustomerChange(group: FormGroup, customerId: string | null) {
    group.patchValue({ selected_invoice_id: '' }, { emitEvent: false });
    const idx = this.rowIndexOf(group);
    if (idx === -1) return;
    if (!customerId) { this.rowOpenInvoices[idx] = []; return; }
    try {
      const res = await this.receivablesService.getInvoices({ customer_id: customerId, status: 'POSTED' });
      this.rowOpenInvoices[idx] = res.results ?? res;
    } catch {
      this.rowOpenInvoices[idx] = [];
    }
  }

  onSpentChange(i: number) {
    const g = this.rowGroup(i);
    if (g.get('spent')?.value) g.patchValue({ received: null });
  }

  onReceivedChange(i: number) {
    const g = this.rowGroup(i);
    if (g.get('received')?.value) g.patchValue({ spent: null });
  }

  private buildPayload(row: any): any {
    const amount = Number(row.spent || row.received || 0);
    const base: any = {
      date: row.date,
      description: row.description || '',
      source_bank_id: this.sourceBankId,
    };
    if (row.reference) base.reference = row.reference;

    if (row.type === 'BANK') {
      if (row.spent) {
        return { ...base, transaction_type: 'TRANSFER',
                 destination_bank_id: row.bank_account_id, transfer_amount: amount };
      } else {
        return { ...base, transaction_type: 'TRANSFER',
                 source_bank_id: row.bank_account_id,
                 destination_bank_id: this.sourceBankId, transfer_amount: amount };
      }
    }

    const splits = [{ account_id: row.account_id, amount, description: row.description || '' }];

    if (row.type === 'SUPPLIER') {
      return { ...base, transaction_type: row.spent ? 'PAYMENT' : 'RECEIPT',
               vendor_id: row.vendor_id,
               splits: [{ account_id: row.contra_account_id, amount, description: row.description || '' }] };
    }
    if (row.type === 'CUSTOMER') {
      return { ...base, transaction_type: row.received ? 'RECEIPT' : 'PAYMENT',
               customer_id: row.customer_id,
               splits: [{ account_id: row.contra_account_id, amount, description: row.description || '' }] };
    }

    return { ...base, transaction_type: row.spent ? 'PAYMENT' : 'RECEIPT', splits };
  }

  // Routes the row through the unified pay/receive service so the resulting BankTransaction,
  // journal entry, and AP/AR history all stay in sync — instead of posting a generic GL split.
  private async submitInvoicePayment(row: any): Promise<void> {
    const amount = Number(row.spent || row.received || 0);
    if (row.type === 'SUPPLIER') {
      await this.payablesService.payInvoice(row.selected_invoice_id, {
        payment_date: row.date,
        amount,
        reference: row.reference || '',
        bank_account_id: this.sourceBankId,
      });
    } else {
      await this.receivablesService.receiveInvoice(row.selected_invoice_id, {
        receipt_date: row.date,
        amount,
        reference: row.reference || '',
        bank_account_id: this.sourceBankId,
      });
    }
  }

  private rowValid(row: any): string | null {
    if (!row.date) return 'Date is required.';
    const amount = Number(row.spent || row.received || 0);
    if (!amount || amount <= 0) return 'Enter a Spent or Received amount.';
    if (row.type === 'BANK' && !row.bank_account_id) return 'Select a bank account.';
    if (row.type === 'LEDGER' && !row.account_id) return 'Select a ledger account.';
    if (row.type === 'SUPPLIER') {
      if (!row.vendor_id) return 'Select a supplier.';
      if (!row.selected_invoice_id && !row.contra_account_id) return 'Select an invoice, or a GL account for a miscellaneous entry.';
    }
    if (row.type === 'CUSTOMER') {
      if (!row.customer_id) return 'Select a customer.';
      if (!row.selected_invoice_id && !row.contra_account_id) return 'Select an invoice, or a GL account for a miscellaneous entry.';
    }
    return null;
  }

  async saveAll() {
    if (!this.sourceBankId) { this.saveError = 'Select a source bank account.'; return; }
    this.saveError = '';
    this.saveResults = [];

    const rowValues = this.rows.controls.map(c => c.value);
    const errors = rowValues.map((r, i) => ({ i, msg: this.rowValid(r) })).filter(e => e.msg);
    if (errors.length) {
      this.saveError = errors.map(e => `Row ${e.i + 1}: ${e.msg}`).join(' | ');
      return;
    }

    this.saving = true;
    let anyFailed = false;

    for (let i = 0; i < rowValues.length; i++) {
      const row = rowValues[i];
      try {
        if (row.selected_invoice_id) {
          await this.submitInvoicePayment(row);
        } else {
          await this.txnService.create(this.buildPayload(row));
        }
        this.saveResults.push({ ok: true, msg: `Row ${i + 1} saved.` });
      } catch (e: any) {
        const msg = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Unknown error';
        this.saveResults.push({ ok: false, msg: `Row ${i + 1}: ${msg}` });
        anyFailed = true;
      }
    }

    this.saving = false;
    if (!anyFailed) {
      this.router.navigate(['/banks/transactions']);
    }
  }
}
