import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import axios from 'axios';
import { BudgetService } from '../../services/budget.service';
import { API_ROOT } from '../../services/api-base';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-budget-list',
  standalone: true,
  imports: [CommonModule, RouterModule, PaginatePipe, PaginationComponent],
  templateUrl: './budget-list.component.html',
})
export class BudgetListComponent implements OnInit {
  budgets: any[] = [];
  loading = true;
  error = '';
  page = 1;
  pageSize = 25;

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

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      const response = await axios.get(`${API_ROOT}budget/budgets/export/`, {
        params: { format }, responseType: 'blob',
      });
      const blob = new Blob([response.data], { type: response.headers['content-type'] });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `budgets.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
