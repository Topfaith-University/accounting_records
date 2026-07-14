import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class PayablesService {
  private base = `${API_ROOT}payables/`;

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

  async downloadInvoicePdf(id: string, invoiceNumber: string): Promise<void> {
    const response = await axios.get(this.base + `invoices/${id}/print/`, { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([response.data], { type: response.headers['content-type'] }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `purchase-invoice-${invoiceNumber}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }

  getItems() { return axios.get(this.base + 'items/').then(r => r.data); }
  getItem(id: string) { return axios.get(this.base + `items/${id}/`).then(r => r.data); }
  createItem(data: object) { return axios.post(this.base + 'items/', data).then(r => r.data); }
  updateItem(id: string, data: object) { return axios.patch(this.base + `items/${id}/`, data).then(r => r.data); }
  deleteItem(id: string) { return axios.delete(this.base + `items/${id}/`).then(r => r.data); }

  async exportInvoices(format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.base + 'invoices/export/', {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `purchase-invoices.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async exportVendors(format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.base + 'vendors/export/', {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vendors.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
