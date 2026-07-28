import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class BudgetService {
  private base = `${API_ROOT}budget/`;

  getAll() { return axios.get(this.base + 'budgets/').then(r => r.data); }
  getOne(id: string) { return axios.get(this.base + `budgets/${id}/`).then(r => r.data); }
  create(data: object) { return axios.post(this.base + 'budgets/', data).then(r => r.data); }
  approve(id: string) { return axios.post(this.base + `budgets/${id}/approve/`).then(r => r.data); }
  deleteBudget(id: string) { return axios.delete(this.base + `budgets/${id}/`).then(r => r.data); }
  getVariance(id: string) { return axios.get(this.base + `budgets/${id}/variance/`).then(r => r.data); }

  async exportFile(format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.base + 'budgets/export/', {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `budgets.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
