import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { ReceivablesService } from '../../services/receivables.service';
import { AccountsService } from '../../services/accounts.service';

@Component({
  selector: 'app-sales-invoice-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './invoice-form.component.html',
})
export class SalesInvoiceFormComponent implements OnInit {
  form!: FormGroup;
  customers: any[] = [];
  accounts: any[] = [];
  saving = false;
  error = '';

  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get total(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.amount) || 0), 0);
  }

  constructor(
    private fb: FormBuilder,
    private receivables: ReceivablesService,
    private accountsService: AccountsService,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      invoice_number: ['', Validators.required],
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      due_date: ['', Validators.required],
      description: [''],
      customer_id: ['', Validators.required],
      ar_account_id: ['', Validators.required],
      lines: this.fb.array([]),
    });
    this.addLine();
    try {
      const [customerData, accountData] = await Promise.all([
        this.receivables.getCustomers(),
        this.accountsService.getAll(),
      ]);
      this.customers = customerData.results ?? customerData;
      this.accounts = accountData.results ?? accountData;
    } catch {
      this.error = 'Failed to load form data. Please refresh.';
    }
  }

  addLine() {
    this.lines.push(this.fb.group({
      revenue_account_id: ['', Validators.required],
      description: [''],
      amount: [null, [Validators.required, Validators.min(0.01)]],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 1) this.lines.removeAt(i);
  }

  async save() {
    if (!this.form.valid || this.saving) return;
    this.saving = true;
    this.error = '';
    try {
      const invoice = await this.receivables.createInvoice(this.form.value);
      this.router.navigate(['/receivables/invoices', invoice.invoice_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }
}
