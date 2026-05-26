import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { PayablesService } from '../../services/payables.service';
import { AccountsService } from '../../services/accounts.service';

@Component({
  selector: 'app-purchase-invoice-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './invoice-form.component.html',
})
export class PurchaseInvoiceFormComponent implements OnInit {
  form!: FormGroup;
  vendors: any[] = [];
  accounts: any[] = [];
  saving = false;
  error = '';

  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get total(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.amount) || 0), 0);
  }

  constructor(
    private fb: FormBuilder,
    private payables: PayablesService,
    private accountsService: AccountsService,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      invoice_number: ['', Validators.required],
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      due_date: ['', Validators.required],
      description: [''],
      vendor_id: ['', Validators.required],
      ap_account_id: ['', Validators.required],
      lines: this.fb.array([]),
    });
    this.addLine();
    const [vendorData, accountData] = await Promise.all([
      this.payables.getVendors(),
      this.accountsService.getAll(),
    ]);
    this.vendors = vendorData.results ?? vendorData;
    this.accounts = (accountData.results ?? accountData);
  }

  addLine() {
    this.lines.push(this.fb.group({
      expense_account_id: ['', Validators.required],
      description: [''],
      amount: [null, [Validators.required, Validators.min(0.01)]],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 1) this.lines.removeAt(i);
  }

  async save() {
    if (!this.form.valid) return;
    this.saving = true;
    this.error = '';
    try {
      const invoice = await this.payables.createInvoice(this.form.value);
      this.router.navigate(['/payables/invoices', invoice.invoice_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }
}
