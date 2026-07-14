import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class AccountsService {
  private baseUrl = `${API_ROOT}accounts/`;

  getAll(params?: { account_type?: string }) {
    return axios.get(this.baseUrl, { params }).then(r => r.data);
  }

  getById(id: string) {
    return axios.get(this.baseUrl + id + '/').then(r => r.data);
  }

  create(data: object) {
    return axios.post(this.baseUrl, data).then(r => r.data);
  }

  update(id: string, data: object) {
    return axios.patch(this.baseUrl + id + '/', data).then(r => r.data);
  }

  delete(id: string) {
    return axios.delete(this.baseUrl + id + '/').then(r => r.data);
  }

  getTypes() {
    return axios.get(this.baseUrl + 'types/').then(r => r.data);
  }

  getLedger(id: string) {
    return axios.get(this.baseUrl + id + '/ledger/').then(r => r.data);
  }

  async exportFile(format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.baseUrl + 'export/', {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `accounts.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
