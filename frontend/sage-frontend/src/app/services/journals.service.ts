import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class JournalsService {
  private baseUrl = 'http://localhost:8002/api/journals/';

  getEntries(params?: { status?: string }) {
    return axios.get(this.baseUrl + 'entries/', { params }).then(r => r.data);
  }

  getEntry(id: string) {
    return axios.get(this.baseUrl + `entries/${id}/`).then(r => r.data);
  }

  createEntry(data: object) {
    return axios.post(this.baseUrl + 'entries/', data).then(r => r.data);
  }

  updateEntry(id: string, data: object) {
    return axios.patch(this.baseUrl + `entries/${id}/`, data).then(r => r.data);
  }

  deleteEntry(id: string) {
    return axios.delete(this.baseUrl + `entries/${id}/`).then(r => r.data);
  }

  postEntry(id: string) {
    return axios.post(this.baseUrl + `entries/${id}/post/`).then(r => r.data);
  }

  voidEntry(id: string) {
    return axios.post(this.baseUrl + `entries/${id}/void/`).then(r => r.data);
  }

  getFiscalYears() {
    return axios.get(this.baseUrl + 'fiscal-years/').then(r => r.data);
  }

  createFiscalYear(data: object) {
    return axios.post(this.baseUrl + 'fiscal-years/', data).then(r => r.data);
  }

  getPeriods(fiscalYearId?: string) {
    const params = fiscalYearId ? { fiscal_year_id: fiscalYearId } : {};
    return axios.get(this.baseUrl + 'periods/', { params }).then(r => r.data);
  }
}
