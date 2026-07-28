# Printable Invoice PDFs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authenticated users download a printable PDF for an individual sales invoice or purchase invoice.

**Architecture:** Add `print` detail actions to the existing DRF invoice viewsets. Each action builds a template context from the existing invoice graph and delegates PDF creation to `config.export_utils.pdf_response`. The two Angular detail pages call service download methods that reuse Axios authentication and the browser blob-download pattern.

**Tech Stack:** Django REST Framework, Django templates, WeasyPrint, Angular 17, Axios, Django `TestCase`/`APIClient`.

## Global Constraints

- Reuse `pdf_response`; add no dependency.
- Preserve list export endpoints and invoice mutation workflows.
- Make no changes outside the files listed below.
- Use the existing Nigerian Naira formatting and invoice data fields.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/payables/views.py` | Add purchase-invoice PDF action and context builder. |
| Modify | `backend/payables/tests.py` | Assert purchase PDF response and missing invoice behavior. |
| Create | `backend/payables/templates/payables/purchase_invoice.html` | Render one vendor-facing purchase invoice. |
| Modify | `backend/receivables/views.py` | Add sales-invoice PDF action and context builder. |
| Modify | `backend/receivables/tests.py` | Assert sales PDF response and missing invoice behavior. |
| Create | `backend/receivables/templates/receivables/sales_invoice.html` | Render one customer-facing sales invoice. |
| Modify | `frontend/sage-frontend/src/app/services/payables.service.ts` | Download one purchase-invoice PDF. |
| Modify | `frontend/sage-frontend/src/app/services/receivables.service.ts` | Download one sales-invoice PDF. |
| Modify | `frontend/sage-frontend/src/app/payables/invoice-detail/invoice-detail.component.ts` | Expose purchase PDF download command. |
| Modify | `frontend/sage-frontend/src/app/payables/invoice-detail/invoice-detail.component.html` | Add purchase PDF command. |
| Modify | `frontend/sage-frontend/src/app/receivables/invoice-detail/invoice-detail.component.ts` | Expose sales PDF download command. |
| Modify | `frontend/sage-frontend/src/app/receivables/invoice-detail/invoice-detail.component.html` | Add sales PDF command. |

### Task 1: Purchase-Invoice Print Endpoint

**Files:**
- Modify: `backend/payables/tests.py`
- Modify: `backend/payables/views.py`
- Create: `backend/payables/templates/payables/purchase_invoice.html`

**Interfaces:**
- Consumes: `PurchaseInvoice.nodes.get_or_none(invoice_id=pk)` and `pdf_response(template, context, filename)`.
- Produces: `GET /api/payables/invoices/<invoice_id>/print/` returning `application/pdf` with `inline; filename="purchase-invoice-<invoice_number>.pdf"`.

- [ ] **Step 1: Write the failing endpoint tests**

  Add a `PurchaseInvoicePrintTests` class which creates a user and API client, patches `payables.views.pdf_response`, and asserts:

  ```python
  @patch('config.export_utils.pdf_response')
  def test_print_returns_purchase_invoice_pdf(self, pdf_response):
      invoice = Mock(invoice_number='PI-0001', total_amount=1500.0, amount_paid=200.0,
                     date='2026-07-01', due_date='2026-07-31', description='', status='POSTED')
      # Patch PurchaseInvoice.nodes.get_or_none and invoice graph relationships.
      response = self.client.get('/api/payables/invoices/invoice-1/print/')
      self.assertEqual(response.status_code, 200)
      pdf_response.assert_called_once()
      self.assertEqual(pdf_response.call_args.args[0], 'payables/purchase_invoice.html')
      self.assertEqual(pdf_response.call_args.args[2], 'purchase-invoice-PI-0001')
      self.assertEqual(pdf_response.call_args.args[1]['outstanding_amount'], 1300.0)
  ```

  Add a separate test with `get_or_none.return_value = None` asserting `404` and `{'detail': 'Not found.'}`.

- [ ] **Step 2: Run the purchase print tests to verify they fail**

  Run: `cd backend && python manage.py test payables.tests.PurchaseInvoicePrintTests -v 2`

  Expected: FAIL because the `print` action and imported `pdf_response` do not exist.

- [ ] **Step 3: Add the minimal action and document template**

  Import `pdf_response` at module scope. Add this detail action to `PurchaseInvoiceViewSet`:

  ```python
  @action(detail=True, methods=['get'], url_path='print')
  def print_invoice(self, request, pk=None):
      invoice = PurchaseInvoice.nodes.get_or_none(invoice_id=pk)
      if not invoice:
          return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
      vendor = invoice.vendor.single()
      lines = list(invoice.lines.all())
      return pdf_response('payables/purchase_invoice.html', {
          'invoice': invoice,
          'vendor': vendor,
          'lines': lines,
          'settled_amount': invoice.amount_paid,
          'outstanding_amount': max(0, invoice.total_amount - invoice.amount_paid),
      }, f'purchase-invoice-{invoice.invoice_number}')
  ```

  Create a self-contained template with a title `Purchase Invoice`, vendor/date/due-date/status metadata, a table with Description, Quantity, Unit Price, and Amount columns, and Total/Paid/Outstanding rows. Use `{{ line.quantity|floatformat:2 }}`, `{{ line.unit_price|floatformat:2 }}`, and `{{ line.amount|floatformat:2 }}`.

- [ ] **Step 4: Run the purchase endpoint tests to verify they pass**

  Run: `cd backend && python manage.py test payables.tests.PurchaseInvoicePrintTests -v 2`

  Expected: PASS with two tests.

- [ ] **Step 5: Commit the completed endpoint**

  ```bash
  git add backend/payables
  git commit -m "feat: add printable purchase invoice PDF"
  ```

### Task 2: Sales-Invoice Print Endpoint

**Files:**
- Modify: `backend/receivables/tests.py`
- Modify: `backend/receivables/views.py`
- Create: `backend/receivables/templates/receivables/sales_invoice.html`

**Interfaces:**
- Consumes: `SalesInvoice.nodes.get_or_none(invoice_id=pk)` and `pdf_response(template, context, filename)`.
- Produces: `GET /api/receivables/invoices/<invoice_id>/print/` returning `application/pdf` with `inline; filename="sales-invoice-<invoice_number>.pdf"`.

- [ ] **Step 1: Write the failing endpoint tests**

  Add `SalesInvoicePrintTests` following Task 1, but set `amount_received=200.0`, assert `sales_invoice.html`, `sales-invoice-SI-0001`, and `outstanding_amount == 1300.0`. Add the 404 test.

- [ ] **Step 2: Run the sales print tests to verify they fail**

  Run: `cd backend && python manage.py test receivables.tests.SalesInvoicePrintTests -v 2`

  Expected: FAIL because the `print` action is unavailable.

- [ ] **Step 3: Add the minimal action and document template**

  Add the equivalent action to `SalesInvoiceViewSet`, using the customer relationship and `amount_received`:

  ```python
  @action(detail=True, methods=['get'], url_path='print')
  def print_invoice(self, request, pk=None):
      invoice = SalesInvoice.nodes.get_or_none(invoice_id=pk)
      if not invoice:
          return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
      customer = invoice.customer.single()
      lines = list(invoice.lines.all())
      return pdf_response('receivables/sales_invoice.html', {
          'invoice': invoice, 'customer': customer, 'lines': lines,
          'settled_amount': invoice.amount_received,
          'outstanding_amount': max(0, invoice.total_amount - invoice.amount_received),
      }, f'sales-invoice-{invoice.invoice_number}')
  ```

  Create the matching template, titled `Sales Invoice`, with customer metadata and Total/Received/Outstanding summary labels.

- [ ] **Step 4: Run the sales endpoint tests to verify they pass**

  Run: `cd backend && python manage.py test receivables.tests.SalesInvoicePrintTests -v 2`

  Expected: PASS with two tests.

- [ ] **Step 5: Commit the completed endpoint**

  ```bash
  git add backend/receivables
  git commit -m "feat: add printable sales invoice PDF"
  ```

### Task 3: Invoice Detail Download Controls

**Files:**
- Modify: `frontend/sage-frontend/src/app/services/payables.service.ts`
- Modify: `frontend/sage-frontend/src/app/services/receivables.service.ts`
- Modify: `frontend/sage-frontend/src/app/payables/invoice-detail/invoice-detail.component.ts`
- Modify: `frontend/sage-frontend/src/app/payables/invoice-detail/invoice-detail.component.html`
- Modify: `frontend/sage-frontend/src/app/receivables/invoice-detail/invoice-detail.component.ts`
- Modify: `frontend/sage-frontend/src/app/receivables/invoice-detail/invoice-detail.component.html`

**Interfaces:**
- Consumes: the endpoints from Tasks 1 and 2.
- Produces: `downloadInvoicePdf(id: string, invoiceNumber: string): Promise<void>` in both services and `downloadPdf()` in both detail components.

- [ ] **Step 1: Write failing service and component tests**

  Add Angular specs that spy on `axios.get`, `URL.createObjectURL`, and `document.createElement`, then assert the sales service requests `receivables/invoices/<id>/print/` with `responseType: 'blob'` and downloads `sales-invoice-<number>.pdf`; assert the purchase service uses the payables path and `purchase-invoice-<number>.pdf`. Add component tests asserting `downloadPdf()` delegates its loaded invoice ID and number to the service.

- [ ] **Step 2: Run the frontend specs to verify they fail**

  Run: `cd frontend/sage-frontend && npm test -- --watch=false --browsers=ChromeHeadless`

  Expected: FAIL because the service and component methods are absent.

- [ ] **Step 3: Implement the download methods and controls**

  Add one method per service:

  ```typescript
  async downloadInvoicePdf(id: string, invoiceNumber: string): Promise<void> {
    const response = await axios.get(this.base + `invoices/${id}/print/`, { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([response.data], { type: response.headers['content-type'] }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `sales-invoice-${invoiceNumber}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }
  ```

  Use `purchase-invoice-` in the payables service. Add `downloadPdf()` to each component to call the relevant service with `this.invoice.invoice_id` and `this.invoice.invoice_number`. Add an icon/text `Print PDF` command in each detail-page header that is available for all invoice statuses and calls `downloadPdf()`.

- [ ] **Step 4: Run the frontend tests and production build**

  Run: `cd frontend/sage-frontend && npm test -- --watch=false --browsers=ChromeHeadless && npm run build`

  Expected: test suite passes and Angular build exits with status `0`.

- [ ] **Step 5: Commit the completed frontend**

  ```bash
  git add frontend/sage-frontend/src/app/services/payables.service.ts frontend/sage-frontend/src/app/services/receivables.service.ts frontend/sage-frontend/src/app/payables/invoice-detail frontend/sage-frontend/src/app/receivables/invoice-detail
  git commit -m "feat: add invoice PDF download controls"
  ```

### Task 4: End-to-End Regression Verification

**Files:** None.

- [ ] **Step 1: Run all relevant backend tests**

  Run: `cd backend && python manage.py test payables receivables -v 2`

  Expected: all tests pass.

- [ ] **Step 2: Inspect the final diff**

  Run: `git diff HEAD~3..HEAD --check && git status --short`

  Expected: no whitespace errors; only intended feature files are committed, while pre-existing user changes remain untouched.

## Plan Self-Review

- Spec coverage: Tasks 1 and 2 implement both authenticated endpoints and templates; Task 3 implements both user commands; Task 4 verifies their affected suites.
- Placeholder scan: no deferred behavior or unbounded implementation steps remain.
- Type consistency: both services use `downloadInvoicePdf(id: string, invoiceNumber: string)` and both components call `downloadPdf()`.
