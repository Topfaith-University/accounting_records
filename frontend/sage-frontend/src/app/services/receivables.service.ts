import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class ReceivablesService {
  private base = 'http://localhost:8002/api/receivables/';

  getCustomers() { return axios.get(this.base + 'customers/').then(r => r.data); }
  getCustomer(id: string) { return axios.get(this.base + `customers/${id}/`).then(r => r.data); }
  createCustomer(data: object) { return axios.post(this.base + 'customers/', data).then(r => r.data); }
  updateCustomer(id: string, data: object) { return axios.patch(this.base + `customers/${id}/`, data).then(r => r.data); }
  deleteCustomer(id: string) { return axios.delete(this.base + `customers/${id}/`).then(r => r.data); }

  getInvoices(params?: object) { return axios.get(this.base + 'invoices/', { params }).then(r => r.data); }
  getInvoice(id: string) { return axios.get(this.base + `invoices/${id}/`).then(r => r.data); }
  createInvoice(data: object) { return axios.post(this.base + 'invoices/', data).then(r => r.data); }
  updateInvoice(id: string, data: object) { return axios.patch(this.base + `invoices/${id}/`, data).then(r => r.data); }
  deleteInvoice(id: string) { return axios.delete(this.base + `invoices/${id}/`).then(r => r.data); }
  postInvoice(id: string) { return axios.post(this.base + `invoices/${id}/post/`).then(r => r.data); }
  voidInvoice(id: string) { return axios.post(this.base + `invoices/${id}/void/`).then(r => r.data); }
  receiveInvoice(id: string, data: object) { return axios.post(this.base + `invoices/${id}/receive/`, data).then(r => r.data); }
}
