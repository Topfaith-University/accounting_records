import axios from 'axios';
import { PayablesService } from './payables.service';

describe('PayablesService', () => {
  it('downloads a purchase invoice PDF', async () => {
    const getSpy = spyOn(axios, 'get').and.resolveTo({
      data: new Uint8Array([1, 2, 3]),
      headers: { 'content-type': 'application/pdf' },
    } as any);
    const createObjectUrlSpy = spyOn(URL, 'createObjectURL').and.returnValue('blob:invoice');
    const revokeObjectUrlSpy = spyOn(URL, 'revokeObjectURL');
    const link = { href: '', download: '', click: jasmine.createSpy('click') } as any;
    spyOn(document, 'createElement').and.returnValue(link);

    await new PayablesService().downloadInvoicePdf('purchase-id', 'PINV-001');

    expect(getSpy).toHaveBeenCalledWith(
      jasmine.stringMatching(/payables\/invoices\/purchase-id\/print\/$/),
      { responseType: 'blob' },
    );
    expect(createObjectUrlSpy).toHaveBeenCalled();
    expect(link.download).toBe('purchase-invoice-PINV-001.pdf');
    expect(link.click).toHaveBeenCalled();
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:invoice');
  });

  it('exports a vendor statement as a blob download', async () => {
    const getSpy = spyOn(axios, 'get').and.resolveTo({
      data: new Uint8Array([1, 2, 3]),
      headers: { 'content-type': 'application/pdf' },
    } as any);
    const createObjectUrlSpy = spyOn(URL, 'createObjectURL').and.returnValue('blob:statement');
    const revokeObjectUrlSpy = spyOn(URL, 'revokeObjectURL');
    const link = { href: '', download: '', click: jasmine.createSpy('click') } as any;
    spyOn(document, 'createElement').and.returnValue(link);

    await new PayablesService().exportVendorStatement('vendor-1', 'pdf');

    expect(getSpy).toHaveBeenCalledWith(
      jasmine.stringMatching(/payables\/vendors\/vendor-1\/statement\/$/),
      { params: { format: 'pdf' }, responseType: 'blob' },
    );
    expect(createObjectUrlSpy).toHaveBeenCalled();
    expect(link.download).toBe('vendor-statement.pdf');
    expect(link.click).toHaveBeenCalled();
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:statement');
  });
});
