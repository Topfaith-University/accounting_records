import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class ReceivablesService {
  private base = `${API_ROOT}receivables/`;

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

  async downloadInvoicePdf(id: string, invoiceNumber: string): Promise<void> {
    const response = await axios.get(this.base + `invoices/${id}/print/`, { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([response.data], { type: response.headers['content-type'] }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `sales-invoice-${invoiceNumber}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async exportCustomers(format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.base + 'customers/export/', {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `customers.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async exportInvoices(format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.base + 'invoices/export/', {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sales-invoices.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  getCustomerStatement(id: string) { return axios.get(this.base + `customers/${id}/statement/`).then(r => r.data); }

  async exportCustomerStatement(id: string, format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.base + `customers/${id}/statement/`, {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `customer-statement.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
