import axios from 'axios';
import { ReceivablesService } from './receivables.service';

describe('ReceivablesService', () => {
  it('downloads a sales invoice PDF', async () => {
    const getSpy = spyOn(axios, 'get').and.resolveTo({
      data: new Uint8Array([1, 2, 3]),
      headers: { 'content-type': 'application/pdf' },
    } as any);
    const createObjectUrlSpy = spyOn(URL, 'createObjectURL').and.returnValue('blob:invoice');
    const revokeObjectUrlSpy = spyOn(URL, 'revokeObjectURL');
    const link = { href: '', download: '', click: jasmine.createSpy('click') } as any;
    spyOn(document, 'createElement').and.returnValue(link);

    await new ReceivablesService().downloadInvoicePdf('sales-id', 'SINV-001');

    expect(getSpy).toHaveBeenCalledWith(
      jasmine.stringMatching(/receivables\/invoices\/sales-id\/print\/$/),
      { responseType: 'blob' },
    );
    expect(createObjectUrlSpy).toHaveBeenCalled();
    expect(link.download).toBe('sales-invoice-SINV-001.pdf');
    expect(link.click).toHaveBeenCalled();
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:invoice');
  });

  it('exports a customer statement as a blob download', async () => {
    const getSpy = spyOn(axios, 'get').and.resolveTo({
      data: new Uint8Array([1, 2, 3]),
      headers: { 'content-type': 'application/pdf' },
    } as any);
    const createObjectUrlSpy = spyOn(URL, 'createObjectURL').and.returnValue('blob:statement');
    const revokeObjectUrlSpy = spyOn(URL, 'revokeObjectURL');
    const link = { href: '', download: '', click: jasmine.createSpy('click') } as any;
    spyOn(document, 'createElement').and.returnValue(link);

    await new ReceivablesService().exportCustomerStatement('customer-1', 'pdf');

    expect(getSpy).toHaveBeenCalledWith(
      jasmine.stringMatching(/receivables\/customers\/customer-1\/statement\/$/),
      { params: { format: 'pdf' }, responseType: 'blob' },
    );
    expect(createObjectUrlSpy).toHaveBeenCalled();
    expect(link.download).toBe('customer-statement.pdf');
    expect(link.click).toHaveBeenCalled();
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:statement');
  });
});
