import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class AccountsService {
  private baseUrl = 'http://localhost:8002/api/accounts/';

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
}
