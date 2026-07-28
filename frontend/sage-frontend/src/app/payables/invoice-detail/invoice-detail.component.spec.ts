import { FormBuilder } from '@angular/forms';
import { InvoiceDetailComponent } from './invoice-detail.component';

describe('InvoiceDetailComponent', () => {
  it('delegates PDF downloads using the loaded purchase invoice', async () => {
    const payables = { downloadInvoicePdf: jasmine.createSpy('downloadInvoicePdf').and.resolveTo() } as any;
    const component = new InvoiceDetailComponent({} as any, payables, {} as any, {} as any, new FormBuilder(), {} as any);
    component.invoice = { invoice_id: 'purchase-id', invoice_number: 'PINV-001' };

    await component.downloadPdf();

    expect(payables.downloadInvoicePdf).toHaveBeenCalledWith('purchase-id', 'PINV-001');
  });
});
