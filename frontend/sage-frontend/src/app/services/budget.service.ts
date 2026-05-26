import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class BudgetService {
  private base = 'http://localhost:8002/api/budget/';

  getAll() { return axios.get(this.base + 'budgets/').then(r => r.data); }
  getOne(id: string) { return axios.get(this.base + `budgets/${id}/`).then(r => r.data); }
  create(data: object) { return axios.post(this.base + 'budgets/', data).then(r => r.data); }
  approve(id: string) { return axios.post(this.base + `budgets/${id}/approve/`).then(r => r.data); }
  deleteBudget(id: string) { return axios.delete(this.base + `budgets/${id}/`).then(r => r.data); }
  getVariance(id: string) { return axios.get(this.base + `budgets/${id}/variance/`).then(r => r.data); }
}
