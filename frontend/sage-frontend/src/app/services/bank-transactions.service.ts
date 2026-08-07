import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class BankTransactionsService {
  private baseUrl = `${API_ROOT}banks/transactions/`;

  getAll(params: { bankAccountId?: string; dateFrom?: string; dateTo?: string; page?: number; pageSize?: number } = {}) {
    const p: Record<string, string | number> = {};
    if (params.bankAccountId) p['bank_account_id'] = params.bankAccountId;
    if (params.dateFrom) p['date_from'] = params.dateFrom;
    if (params.dateTo) p['date_to'] = params.dateTo;
    if (params.page) p['page'] = params.page;
    if (params.pageSize) p['page_size'] = params.pageSize;
    return axios.get(this.baseUrl, { params: p }).then(r => r.data);
  }

  exportFile(params: Record<string, string>, format: 'csv' | 'xlsx', filename: string): Promise<void> {
    return axios.get(this.baseUrl + 'export/', {
      params: { ...params, format },
      responseType: 'blob',
    }).then(response => {
      const blob = new Blob([response.data], { type: response.headers['content-type'] });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  getOne(id: string) {
    return axios.get(this.baseUrl + `${id}/`).then(r => r.data);
  }

  create(data: object) {
    return axios.post(this.baseUrl, data).then(r => r.data);
  }

  importCsv(formData: FormData) {
    return axios.post(this.baseUrl + 'import/', formData).then(r => r.data);
  }
}
