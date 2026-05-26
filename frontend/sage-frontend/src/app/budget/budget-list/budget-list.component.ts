import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { BudgetService } from '../../services/budget.service';

@Component({
  selector: 'app-budget-list',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './budget-list.component.html',
})
export class BudgetListComponent implements OnInit {
  budgets: any[] = [];
  loading = true;
  error = '';

  constructor(private budgetService: BudgetService) {}

  async ngOnInit() {
    try {
      const data = await this.budgetService.getAll();
      this.budgets = data.results ?? data;
    } catch {
      this.error = 'Failed to load budgets.';
    } finally {
      this.loading = false;
    }
  }

  statusColor(s: string) {
    return s === 'APPROVED' ? '#10b981' : '#f59e0b';
  }
}
