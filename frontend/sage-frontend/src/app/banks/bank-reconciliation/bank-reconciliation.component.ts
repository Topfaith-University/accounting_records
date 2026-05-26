import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { BanksService } from '../../services/banks.service';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-bank-reconciliation',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './bank-reconciliation.component.html',
})
export class BankReconciliationComponent implements OnInit {
  recon: any = null;
  lines: any[] = [];
  loading = true;
  error = '';
  completing = false;
  completeError = '';

  private id = '';

  constructor(
    private route: ActivatedRoute,
    private banksService: BanksService,
    private auth: AuthService,
  ) {}

  async ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    try {
      const data = await this.banksService.getReconciliation(this.id);
      this.recon = data;
      this.lines = data.lines ?? [];
    } catch {
      this.error = 'Failed to load reconciliation.';
    } finally {
      this.loading = false;
    }
  }

  get isManagerOrAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Admin', 'Manager'].includes(r)) ?? false;
  }

  get reconciledDebits(): number {
    return this.lines
      .filter(l => l.is_reconciled && l.side === 'DEBIT')
      .reduce((sum, l) => sum + +l.amount, 0);
  }

  get reconciledCredits(): number {
    return this.lines
      .filter(l => l.is_reconciled && l.side === 'CREDIT')
      .reduce((sum, l) => sum + +l.amount, 0);
  }

  get difference(): number {
    return Math.abs(this.reconciledDebits - this.reconciledCredits - +(this.recon?.statement_balance ?? 0));
  }

  get isBalanced(): boolean {
    return Math.abs(this.difference) < 0.01;
  }

  async toggleLine(line: any) {
    if (this.recon?.status === 'COMPLETED') return;
    try {
      const result = await this.banksService.toggleLine(this.recon.reconciliation_id, line.line_id);
      line.is_reconciled = result.is_reconciled;
    } catch {
      this.error = 'Failed to toggle line.';
    }
  }

  async complete() {
    if (!this.isBalanced || this.recon?.status !== 'DRAFT') return;
    this.completing = true;
    this.completeError = '';
    try {
      const updated = await this.banksService.completeReconciliation(this.id);
      this.recon = { ...this.recon, ...updated };
    } catch (e: any) {
      this.completeError = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Failed to complete reconciliation.';
    } finally {
      this.completing = false;
    }
  }

  sideColor(side: string): string {
    if (side === 'DEBIT') return '#1a73e8';
    if (side === 'CREDIT') return '#10b981';
    return '#333';
  }

  statusColor(status: string): string {
    if (status === 'COMPLETED') return '#10b981';
    if (status === 'DRAFT') return '#f59e0b';
    return '#888';
  }
}
