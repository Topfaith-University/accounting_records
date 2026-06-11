import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { PayablesService } from '../../services/payables.service';
import { AuthService } from '../../services/auth.service';
import { BanksService } from '../../services/banks.service';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';

@Component({
  selector: 'app-invoice-detail',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, BankSelectComponent],
  templateUrl: './invoice-detail.component.html',
})
export class InvoiceDetailComponent implements OnInit {
  invoice: any = null;
  loading = true;
  error = '';
  actionError = '';
  allBanks: any[] = [];
  showPayForm = false;
  paying = false;
  payForm!: FormGroup;

  get isManagerOrAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Manager', 'Admin'].includes(r)) ?? false;
  }

  get remaining(): number {
    if (!this.invoice) return 0;
    return Math.max(0, this.invoice.total_amount - this.invoice.amount_paid);
  }

  constructor(
    private route: ActivatedRoute,
    private payables: PayablesService,
    private auth: AuthService,
    private banks: BanksService,
    private fb: FormBuilder,
    private router: Router,
  ) {}

  async ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.payForm = this.fb.group({
      payment_date: [new Date().toISOString().slice(0, 10), Validators.required],
      amount: [null, [Validators.required, Validators.min(0.01)]],
      reference: [''],
      bank_account_id: ['', Validators.required],
    });
    try {
      [this.invoice, this.allBanks] = await Promise.all([
        this.payables.getInvoice(id),
        this.banks.getAccounts().then((d: any) => d.results ?? d),
      ]);
      this.invoice.lines = this.invoice.lines ?? [];
      this.payForm.patchValue({ amount: this.remaining });
    } catch { this.error = 'Invoice not found.'; }
    finally { this.loading = false; }
  }

  async postInvoice() {
    try {
      this.invoice = await this.payables.postInvoice(this.invoice.invoice_id);
      this.actionError = '';
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Post failed.';
    }
  }

  async voidInvoice() {
    if (!confirm('Void this invoice?')) return;
    try {
      this.invoice = await this.payables.voidInvoice(this.invoice.invoice_id);
      this.actionError = '';
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Void failed.';
    }
  }

  editInvoice() {
    this.router.navigate(['/payables/invoices', this.invoice.invoice_id, 'edit']);
  }

  async deleteInvoice() {
    if (!confirm('Delete this draft invoice? This cannot be undone.')) return;
    try {
      await this.payables.deleteInvoice(this.invoice.invoice_id);
      this.router.navigate(['/payables/invoices']);
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Delete failed.';
    }
  }

  async pay() {
    if (!this.payForm.valid) return;
    this.paying = true;
    this.actionError = '';
    try {
      await this.payables.payInvoice(this.invoice.invoice_id, this.payForm.value);
      this.invoice = await this.payables.getInvoice(this.invoice.invoice_id);
      this.showPayForm = false;
      this.payForm.patchValue({ amount: this.remaining });
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Payment failed.';
    } finally { this.paying = false; }
  }

  statusColor(s: string) {
    return { DRAFT: '#f59e0b', POSTED: '#1a73e8', PAID: '#10b981', VOID: '#ef4444' }[s] ?? '#888';
  }
}
