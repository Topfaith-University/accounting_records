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
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      description: [''],
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
    if (this.splits.length === 0) {
      this.addSplit();
    }
  }

  removeSplit(i: number) {
    if (this.splits.length > 1) this.splits.removeAt(i);
  }

  async submit() {
    if (this.form.invalid) return;
    const val = this.form.value;
    this.saving = true;
    this.error = '';
    const payload: any = {
      transaction_type: val.transaction_type,
      date: val.date,
      description: val.description,
      source_bank_id: val.source_bank_id,
      splits: val.splits.map((s: any) => ({
        account_id: s.account_id,
        amount: Number(s.amount),
        description: s.description,
      })),
    };
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
