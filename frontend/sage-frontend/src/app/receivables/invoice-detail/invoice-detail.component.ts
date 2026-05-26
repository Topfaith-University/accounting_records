import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ReceivablesService } from '../../services/receivables.service';
import { AuthService } from '../../services/auth.service';
import { BanksService } from '../../services/banks.service';

@Component({
  selector: 'app-sales-invoice-detail',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './invoice-detail.component.html',
})
export class SalesInvoiceDetailComponent implements OnInit {
  invoice: any = null;
  loading = true;
  error = '';
  actionError = '';
  bankAccounts: any[] = [];
  showReceiveForm = false;
  receiving = false;
  receiveForm!: FormGroup;

  get isManagerOrAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Manager', 'Admin'].includes(r)) ?? false;
  }

  get remaining(): number {
    if (!this.invoice) return 0;
    return Math.max(0, this.invoice.total_amount - this.invoice.amount_received);
  }

  constructor(
    private route: ActivatedRoute,
    private receivables: ReceivablesService,
    private auth: AuthService,
    private banks: BanksService,
    private fb: FormBuilder,
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
      [this.invoice, this.bankAccounts] = await Promise.all([
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
