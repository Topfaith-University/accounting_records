import { FormBuilder } from '@angular/forms';
import { SalesInvoiceDetailComponent } from './invoice-detail.component';

describe('SalesInvoiceDetailComponent', () => {
  it('delegates PDF downloads using the loaded sales invoice', async () => {
    const receivables = { downloadInvoicePdf: jasmine.createSpy('downloadInvoicePdf').and.resolveTo() } as any;
    const component = new SalesInvoiceDetailComponent({} as any, receivables, {} as any, {} as any, new FormBuilder(), {} as any);
    component.invoice = { invoice_id: 'sales-id', invoice_number: 'SINV-001' };

    await component.downloadPdf();

    expect(receivables.downloadInvoicePdf).toHaveBeenCalledWith('sales-id', 'SINV-001');
  });
});
