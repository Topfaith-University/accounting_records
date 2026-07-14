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
});
