import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class BankTransactionsService {
  private baseUrl = 'http://localhost:8002/api/banks/transactions/';

  getAll(bankAccountId?: string) {
    const params = bankAccountId ? { bank_account_id: bankAccountId } : {};
    return axios.get(this.baseUrl, { params }).then(r => r.data);
  }

  getOne(id: string) {
    return axios.get(this.baseUrl + `${id}/`).then(r => r.data);
  }

  create(data: object) {
    return axios.post(this.baseUrl, data).then(r => r.data);
  }
}
