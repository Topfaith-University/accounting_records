import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class JournalsService {
  private baseUrl = `${API_ROOT}journals/`;

  getEntries(params?: { status?: string; date_from?: string; date_to?: string; search?: string; page?: number; page_size?: number }) {
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

  async exportFile(format: 'pdf' | 'xlsx', params?: { date_from?: string; date_to?: string }): Promise<void> {
    const response = await axios.get(this.baseUrl + 'entries/export/', {
      params: { format, ...params },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `journal-entries.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
