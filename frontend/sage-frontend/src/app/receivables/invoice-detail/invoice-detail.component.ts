import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ReceivablesService } from '../../services/receivables.service';
import { BanksService } from '../../services/banks.service';
import { BankSelectComponent } from '../../shared/bank-select/bank-select.component';

@Component({
  selector: 'app-sales-invoice-detail',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, BankSelectComponent],
  templateUrl: './invoice-detail.component.html',
})
export class SalesInvoiceDetailComponent implements OnInit {
  invoice: any = null;
  loading = true;
  error = '';
  actionError = '';
  allBanks: any[] = [];
  showReceiveForm = false;
  receiving = false;
  receiveForm!: FormGroup;

  get remaining(): number {
    if (!this.invoice) return 0;
    return Math.max(0, this.invoice.total_amount - this.invoice.amount_received);
  }

  constructor(
    private route: ActivatedRoute,
    private receivables: ReceivablesService,
    private banks: BanksService,
    private fb: FormBuilder,
    private router: Router,
  ) {}

  async ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.receiveForm = this.fb.group({
      receipt_date: [new Date().toISOString().slice(0, 10), Validators.required],
      amount: [null, [Validators.required, Validators.min(0.01)]],
      reference: [''],
      bank_account_id: ['', Validators.required],
    });
    try {
      [this.invoice, this.allBanks] = await Promise.all([
        this.receivables.getInvoice(id),
        this.banks.getAccounts().then((d: any) => d.results ?? d),
      ]);
      this.invoice.lines = this.invoice.lines ?? [];
      this.receiveForm.patchValue({ amount: this.remaining });
    } catch { this.error = 'Invoice not found.'; }
    finally { this.loading = false; }
  }

  async postInvoice() {
    try {
      this.invoice = await this.receivables.postInvoice(this.invoice.invoice_id);
      this.actionError = '';
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Post failed.';
    }
  }

  async voidInvoice() {
    if (!confirm('Void this invoice?')) return;
    try {
      this.invoice = await this.receivables.voidInvoice(this.invoice.invoice_id);
      this.actionError = '';
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Void failed.';
    }
  }

  async downloadPdf() {
    await this.receivables.downloadInvoicePdf(this.invoice.invoice_id, this.invoice.invoice_number);
  }

  editInvoice() {
    this.router.navigate(['/receivables/invoices', this.invoice.invoice_id, 'edit']);
  }

  async deleteInvoice() {
    if (!confirm('Delete this draft invoice? This cannot be undone.')) return;
    try {
      await this.receivables.deleteInvoice(this.invoice.invoice_id);
      this.router.navigate(['/receivables/invoices']);
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Delete failed.';
    }
  }

  async receive() {
    if (!this.receiveForm.valid) return;
    this.receiving = true;
    this.actionError = '';
    try {
      await this.receivables.receiveInvoice(this.invoice.invoice_id, this.receiveForm.value);
      this.invoice = await this.receivables.getInvoice(this.invoice.invoice_id);
      this.showReceiveForm = false;
      this.receiveForm.patchValue({ amount: this.remaining });
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Receipt failed.';
    } finally { this.receiving = false; }
  }

  statusColor(s: string) {
    return { DRAFT: '#f59e0b', POSTED: '#1a73e8', PAID: '#10b981', VOID: '#ef4444' }[s] ?? '#888';
  }
}
