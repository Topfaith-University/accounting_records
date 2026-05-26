import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class ReportsService {
  private base = 'http://localhost:8002/api/reports/';

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

  exportUrl(
    report: 'trial-balance' | 'income-statement' | 'balance-sheet' | 'gl-detail',
    params: Record<string, string>,
    format: 'pdf' | 'xlsx',
  ): string {
    const q = new URLSearchParams({ ...params, format }).toString();
    return `${this.base}${report}/?${q}`;
  }
}
