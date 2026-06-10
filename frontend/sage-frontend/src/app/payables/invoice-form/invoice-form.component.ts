import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { PayablesService } from '../../services/payables.service';
import { AccountsService } from '../../services/accounts.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';

@Component({
  selector: 'app-purchase-invoice-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AccountSelectComponent],
  templateUrl: './invoice-form.component.html',
})
export class PurchaseInvoiceFormComponent implements OnInit {
  form!: FormGroup;
  vendors: any[] = [];
  accounts: any[] = [];
  allAccounts: any[] = [];
  saving = false;
  error = '';
  invoiceId: string | null = null;

  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get total(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.amount) || 0), 0);
  }

  get isEditMode(): boolean {
    return !!this.invoiceId;
  }

  constructor(
    private fb: FormBuilder,
    private payables: PayablesService,
    private accountsService: AccountsService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      due_date: ['', Validators.required],
      description: [''],
      vendor_id: ['', Validators.required],
      ap_account_id: ['', Validators.required],
      lines: this.fb.array([]),
    });
    this.addLine();
    try {
      const [vendorData, accountData] = await Promise.all([
        this.payables.getVendors(),
        this.accountsService.getAll(),
      ]);
      this.vendors = vendorData.results ?? vendorData;
      this.accounts = accountData.results ?? accountData;
      this.allAccounts = [...this.accounts];
      this.invoiceId = this.route.snapshot.paramMap.get('id');
      if (this.invoiceId) {
        const invoice = await this.payables.getInvoice(this.invoiceId);
        this.form.patchValue({
          date: invoice.date ?? '',
          due_date: invoice.due_date ?? '',
          description: invoice.description ?? '',
          vendor_id: invoice.vendor_id ?? '',
          ap_account_id: invoice.ap_account_id ?? '',
        });
        this.lines.clear();
        for (const line of (invoice.lines ?? [])) {
          this.lines.push(this.fb.group({
            expense_account_id: [line.expense_account_id ?? '', Validators.required],
            description: [line.description ?? ''],
            amount: [line.amount ?? null, [Validators.required, Validators.min(0.01)]],
          }));
        }
        if (this.lines.length === 0) {
          this.addLine();
        }
      }
    } catch {
      this.error = 'Failed to load form data. Please refresh.';
    }
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
    if (!this.form.valid || this.saving) return;
    this.saving = true;
    this.error = '';
    try {
      const invoice = this.invoiceId
        ? await this.payables.updateInvoice(this.invoiceId, this.form.value)
        : await this.payables.createInvoice(this.form.value);
      this.router.navigate(['/payables/invoices', invoice.invoice_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }
}
