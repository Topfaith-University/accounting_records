import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class ReportsService {
  private base = `${API_ROOT}reports/`;

  getTrialBalance(dateFrom: string, dateTo: string) {
    return axios.get(this.base + 'trial-balance/', {
      params: { date_from: dateFrom, date_to: dateTo },
    }).then(r => r.data);
  }

  getIncomeStatement(dateFrom: string, dateTo: string) {
    return axios.get(this.base + 'income-statement/', {
      params: { date_from: dateFrom, date_to: dateTo },
    }).then(r => r.data);
  }

  getBalanceSheet(asOfDate: string) {
    return axios.get(this.base + 'balance-sheet/', {
      params: { as_of_date: asOfDate },
    }).then(r => r.data);
  }

  getGlDetail(accountId: string, dateFrom: string, dateTo: string) {
    return axios.get(this.base + 'gl-detail/', {
      params: { account_id: accountId, date_from: dateFrom, date_to: dateTo },
    }).then(r => r.data);
  }

  async exportFile(
    report: 'trial-balance' | 'income-statement' | 'balance-sheet' | 'gl-detail',
    params: Record<string, string>,
    format: 'pdf' | 'xlsx',
    filename: string,
  ): Promise<void> {
    const response = await axios.get(this.base + report + '/', {
      params: { ...params, format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
