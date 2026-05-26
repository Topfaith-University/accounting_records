import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { BudgetService } from '../../services/budget.service';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-budget-detail',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './budget-detail.component.html',
})
export class BudgetDetailComponent implements OnInit {
  budget: any = null;
  variance: any = null;
  loading = true;
  error = '';
  approving = false;
  actionError = '';
  activeTab: 'lines' | 'variance' = 'lines';

  get isManagerOrAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return user?.roles.some((r: string) => ['Manager', 'Admin'].includes(r)) ?? false;
  }

  constructor(
    private route: ActivatedRoute,
    private budgetService: BudgetService,
    private auth: AuthService,
  ) {}

  async ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    try {
      this.budget = await this.budgetService.getOne(id);
      this.budget.lines = this.budget.lines ?? [];
    } catch {
      this.error = 'Budget not found.';
    } finally {
      this.loading = false;
    }
  }

  async loadVariance() {
    if (this.variance) return;
    this.actionError = '';
    try {
      this.variance = await this.budgetService.getVariance(this.budget.budget_id);
    } catch {
      this.actionError = 'Failed to load variance report.';
    }
  }

  async setTab(tab: string) {
    this.activeTab = tab as typeof this.activeTab;
    if (tab === 'variance') await this.loadVariance();
  }

  async approve() {
    this.approving = true;
    this.actionError = '';
    try {
      this.budget = await this.budgetService.approve(this.budget.budget_id);
      this.budget.lines = this.budget.lines ?? [];
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Approval failed.';
    } finally {
      this.approving = false;
    }
  }

  statusColor(s: string) {
    return s === 'APPROVED' ? '#10b981' : '#f59e0b';
  }

  varianceColor(v: number) {
    return v >= 0 ? '#10b981' : '#ef4444';
  }
}
