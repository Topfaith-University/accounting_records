import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class PayablesService {
  private base = 'http://localhost:8002/api/payables/';

  getVendors() { return axios.get(this.base + 'vendors/').then(r => r.data); }
  getVendor(id: string) { return axios.get(this.base + `vendors/${id}/`).then(r => r.data); }
  createVendor(data: object) { return axios.post(this.base + 'vendors/', data).then(r => r.data); }
  updateVendor(id: string, data: object) { return axios.patch(this.base + `vendors/${id}/`, data).then(r => r.data); }
  deleteVendor(id: string) { return axios.delete(this.base + `vendors/${id}/`).then(r => r.data); }

  getInvoices(params?: object) { return axios.get(this.base + 'invoices/', { params }).then(r => r.data); }
  getInvoice(id: string) { return axios.get(this.base + `invoices/${id}/`).then(r => r.data); }
  createInvoice(data: object) { return axios.post(this.base + 'invoices/', data).then(r => r.data); }
  updateInvoice(id: string, data: object) { return axios.patch(this.base + `invoices/${id}/`, data).then(r => r.data); }
  deleteInvoice(id: string) { return axios.delete(this.base + `invoices/${id}/`).then(r => r.data); }
  postInvoice(id: string) { return axios.post(this.base + `invoices/${id}/post/`).then(r => r.data); }
  voidInvoice(id: string) { return axios.post(this.base + `invoices/${id}/void/`).then(r => r.data); }
  payInvoice(id: string, data: object) { return axios.post(this.base + `invoices/${id}/pay/`, data).then(r => r.data); }
}
