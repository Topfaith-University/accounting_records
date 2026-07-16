import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ReceivablesService } from '../../services/receivables.service';
import { AccountsService } from '../../services/accounts.service';
import { PayablesService } from '../../services/payables.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
import { CustomerSelectComponent } from '../../shared/customer-select/customer-select.component';
import { ItemSelectComponent } from '../../shared/item-select/item-select.component';

@Component({
  selector: 'app-sales-invoice-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AccountSelectComponent, CustomerSelectComponent, ItemSelectComponent],
  templateUrl: './invoice-form.component.html',
})
export class SalesInvoiceFormComponent implements OnInit {
  form!: FormGroup;
  customers: any[] = [];
  allCustomers: any[] = [];
  accounts: any[] = [];
  allAccounts: any[] = [];
  items: any[] = [];
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
    private receivables: ReceivablesService,
    private accountsService: AccountsService,
    private payables: PayablesService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      due_date: ['', Validators.required],
      description: [''],
      customer_id: ['', Validators.required],
      ar_account_id: ['', Validators.required],
      lines: this.fb.array([]),
    });
    this.addLine();
    try {
      const [customerData, accountData, itemData] = await Promise.all([
        this.receivables.getCustomers(),
        this.accountsService.getAll(),
        this.payables.getItems(),
      ]);
      this.customers = customerData.results ?? customerData;
      this.allCustomers = [...this.customers];
      this.accounts = accountData.results ?? accountData;
      this.allAccounts = [...this.accounts];
      this.items = itemData.results ?? itemData;
      this.invoiceId = this.route.snapshot.paramMap.get('id');
      if (this.invoiceId) {
        const invoice = await this.receivables.getInvoice(this.invoiceId);
        this.form.patchValue({
          date: invoice.date ?? '',
          due_date: invoice.due_date ?? '',
          description: invoice.description ?? '',
          customer_id: invoice.customer_id ?? '',
          ar_account_id: invoice.ar_account_id ?? '',
        });
        this.lines.clear();
        for (const line of (invoice.lines ?? [])) {
          this.lines.push(this.fb.group({
            revenue_account_id: [line.revenue_account_id ?? '', Validators.required],
            description: [line.description ?? ''],
            quantity: [line.quantity ?? 1, [Validators.required, Validators.min(0.01)]],
            unit_price: [line.unit_price ?? 0, [Validators.required, Validators.min(0)]],
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
      revenue_account_id: ['', Validators.required],
      description: [''],
      quantity: [1, [Validators.required, Validators.min(0.01)]],
      unit_price: [0, [Validators.required, Validators.min(0)]],
      amount: [null, [Validators.required, Validators.min(0.01)]],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 1) this.lines.removeAt(i);
  }

  recomputeAmount(index: number) {
    const group = this.lines.at(index);
    const qty = group.get('quantity')!.value || 0;
    const price = group.get('unit_price')!.value || 0;
    group.get('amount')!.setValue(Math.round(qty * price * 100) / 100);
  }

  applyItem(index: number, itemId: string) {
    const item = this.items.find(i => i.item_id === itemId);
    if (!item) return;
    const group = this.lines.at(index);
    group.patchValue({
      revenue_account_id: item.revenue_account_id ?? '',
      description: item.name,
      unit_price: item.selling_price ?? 0,
    });
    this.recomputeAmount(index);
  }

  async save() {
    if (!this.form.valid || this.saving) return;
    this.saving = true;
    this.error = '';
    try {
      const invoice = this.invoiceId
        ? await this.receivables.updateInvoice(this.invoiceId, this.form.value)
        : await this.receivables.createInvoice(this.form.value);
      this.router.navigate(['/receivables/invoices', invoice.invoice_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }
}
