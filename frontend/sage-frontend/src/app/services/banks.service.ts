import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class BanksService {
  private baseUrl = `${API_ROOT}banks/`;

  getAccounts() {
    return axios.get(this.baseUrl + 'accounts/').then(r => r.data);
  }

  getAccount(id: string) {
    return axios.get(this.baseUrl + `accounts/${id}/`).then(r => r.data);
  }

  createAccount(data: object) {
    return axios.post(this.baseUrl + 'accounts/', data).then(r => r.data);
  }

  updateAccount(id: string, data: object) {
    return axios.patch(this.baseUrl + `accounts/${id}/`, data).then(r => r.data);
  }

  deleteAccount(id: string) {
    return axios.delete(this.baseUrl + `accounts/${id}/`).then(r => r.data);
  }

  getAccountLedger(id: string) {
    return axios.get(this.baseUrl + `accounts/${id}/ledger/`).then(r => r.data);
  }

  getAccountReconciliations(id: string) {
    return axios.get(this.baseUrl + `accounts/${id}/reconciliations/`).then(r => r.data);
  }

  getReconciliation(id: string) {
    return axios.get(this.baseUrl + `reconciliations/${id}/`).then(r => r.data);
  }

  createReconciliation(data: object) {
    return axios.post(this.baseUrl + 'reconciliations/', data).then(r => r.data);
  }

  toggleLine(reconId: string, lineId: string) {
    return axios.post(this.baseUrl + `reconciliations/${reconId}/toggle-line/`, { line_id: lineId }).then(r => r.data);
  }

  completeReconciliation(id: string) {
    return axios.post(this.baseUrl + `reconciliations/${id}/complete/`).then(r => r.data);
  }

  async exportFile(format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.baseUrl + 'accounts/export/', {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bank-accounts.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
