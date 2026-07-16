# Vendor & Customer Statement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each vendor and customer a detail page showing their own transaction ledger (invoices + payments/receipts) with a running balance, reachable via a "Statement" button on the vendor/customer list rows.

**Architecture:** Two new read-only Django REST actions (`GET /api/payables/vendors/{id}/statement/`, `GET /api/receivables/customers/{id}/statement/`) compute the ledger directly from existing domain relationships (`Vendor.invoices`, `PurchaseInvoice.payments`, `Customer.invoices`, `SalesInvoice.receipts`) — not from shared GL account lines, which would blend other vendors'/customers' activity together. Two new Angular routes/components render the ledger and offer PDF/XLSX export using the project's existing blob-download pattern.

**Tech Stack:** Django REST Framework + neomodel (Neo4j) on the backend; Angular 17 standalone components + axios on the frontend.

## Global Constraints

- Only `POSTED` and `PAID` invoices count toward the ledger and running balance — `DRAFT` and `VOID` invoices are excluded entirely (spec: "Data model & computation approach").
- Vendor ledger uses AP's credit-normal convention: invoices are CREDIT lines, payments are DEBIT lines, `running_balance += credit - debit`.
- Customer ledger uses AR's debit-normal convention: invoices are DEBIT lines, receipts are CREDIT lines, `running_balance += debit - credit`.
- Do not read from `AFFECTS_ACCOUNT` / GL account lines for either ledger — this is the exact "mopped balance" problem the design is deliberately avoiding.
- New endpoints follow the existing `?format=json|pdf|xlsx` convention (default `json`) already used by `reports/gl-detail` and reuse `xlsx_response`/`pdf_response` from `config/export_utils.py` — no new export mechanism.
- No RBAC restriction beyond `IsAuthenticated` (read-only, same tier as vendor/customer/invoice list views).
- No changes to invoice/payment/receipt posting logic in `payables/services.py` or `receivables/services.py` beyond adding the two new statement functions.

---

## Task 1: Vendor Statement — Backend

**Files:**
- Modify: `backend/payables/services.py:3` (import), append new function at end (after line 169)
- Modify: `backend/payables/views.py:79` (insert new action between `destroy` and `export` in `VendorViewSet`)
- Create: `backend/payables/templates/payables/vendor_statement.html`
- Test: `backend/payables/tests.py` (append new `TestCase` class at end of file)

**Interfaces:**
- Produces: `payables.services.get_vendor_statement(vendor_id: str, company_id: str) -> dict | None`. Returns `None` if the vendor doesn't exist in that company. Otherwise:
  ```python
  {
    'entity_id': str,
    'entity_name': str,
    'lines': [
      {'date': str, 'type': 'INVOICE' | 'PAYMENT', 'reference': str,
       'description': str, 'debit': float, 'credit': float, 'running_balance': float},
      ...
    ],
    'closing_balance': float,
  }
  ```
- Produces: `GET /api/payables/vendors/{id}/statement/` (default JSON), `?format=pdf`, `?format=xlsx`.
- Consumes: existing `Vendor.invoices` (`RelationshipFrom(PurchaseInvoice, 'FROM_VENDOR')`), `PurchaseInvoice.payments` (`RelationshipFrom(APPayment, 'PAYS_INVOICE')`), and `xlsx_response`/`pdf_response` from `config.export_utils`.

- [ ] **Step 1: Write the failing tests**

Open `backend/payables/tests.py` and append this class at the end of the file:

```python
class VendorStatementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _post_invoice(self, vendor_id, amount, suffix=''):
        ap = self.client.post('/api/accounts/', {
            'name': f'AP Control{suffix}', 'account_type': 'Current Liabilities', 'normal_balance': 'CREDIT',
        }, format='json').data
        expense = self.client.post('/api/accounts/', {
            'name': f'Expense{suffix}', 'account_type': 'Expenses', 'normal_balance': 'DEBIT',
        }, format='json').data
        invoice = self.client.post('/api/payables/invoices/', {
            'date': '2026-01-01', 'due_date': '2026-02-01',
            'vendor_id': vendor_id, 'ap_account_id': ap['account_id'],
            'lines': [{'description': 'Line item', 'amount': amount, 'expense_account_id': expense['account_id']}],
        }, format='json').data
        return invoice

    def test_statement_running_balance_after_partial_payment(self):
        import uuid
        vendor = self.client.post('/api/payables/vendors/', {'name': 'Test Vendor'}, format='json').data
        invoice = self._post_invoice(vendor['vendor_id'], 1000.0)
        self.client.post(f"/api/payables/invoices/{invoice['invoice_id']}/post/")

        bank_gl = self.client.post('/api/accounts/', {
            'name': 'Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json').data
        bank = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank', 'bank_name': 'GTBank', 'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 5000.0, 'opening_balance_date': '2026-01-01',
            'gl_account_id_input': bank_gl['account_id'],
        }, format='json').data
        self.client.post(f"/api/payables/invoices/{invoice['invoice_id']}/pay/", {
            'payment_date': '2026-01-15', 'amount': 400.0, 'bank_account_id': bank['bank_account_id'],
        }, format='json')

        resp = self.client.get(f"/api/payables/vendors/{vendor['vendor_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        lines = resp.data['lines']
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['type'], 'INVOICE')
        self.assertEqual(lines[0]['credit'], 1000.0)
        self.assertEqual(lines[0]['debit'], 0.0)
        self.assertEqual(lines[0]['running_balance'], 1000.0)
        self.assertEqual(lines[1]['type'], 'PAYMENT')
        self.assertEqual(lines[1]['debit'], 400.0)
        self.assertEqual(lines[1]['running_balance'], 600.0)
        self.assertEqual(resp.data['closing_balance'], 600.0)

    def test_statement_excludes_draft_invoices(self):
        vendor = self.client.post('/api/payables/vendors/', {'name': 'Draft Vendor'}, format='json').data
        self._post_invoice(vendor['vendor_id'], 500.0, suffix=' Draft')  # left unposted (DRAFT)

        resp = self.client.get(f"/api/payables/vendors/{vendor['vendor_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['lines'], [])
        self.assertEqual(resp.data['closing_balance'], 0.0)

    def test_statement_returns_404_for_unknown_vendor(self):
        resp = self.client.get('/api/payables/vendors/does-not-exist/statement/')
        self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker exec django_backend python manage.py test payables.tests.VendorStatementTests -v 2`

Expected: `test_statement_running_balance_after_partial_payment` and `test_statement_excludes_draft_invoices` FAIL with `AssertionError: 404 != 200` (the `statement` action doesn't exist yet, so DRF's router 404s). `test_statement_returns_404_for_unknown_vendor` will already PASS at this stage — that's expected and fine, since a missing route and a missing vendor both currently 404 for different reasons; it becomes a real regression test once Step 3-4 land.

- [ ] **Step 3: Implement `get_vendor_statement`**

In `backend/payables/services.py`, change the import line at the top:

```python
from .models import PurchaseInvoice, APPayment, Vendor
```

Then append this function at the end of the file:

```python
def get_vendor_statement(vendor_id: str, company_id: str) -> dict | None:
    vendor = Vendor.nodes.get_or_none(vendor_id=vendor_id, company_id=company_id)
    if not vendor:
        return None

    invoices = [i for i in vendor.invoices.all() if i.status in ('POSTED', 'PAID')]

    events = []
    for invoice in invoices:
        events.append({
            'date': invoice.date,
            'type': 'INVOICE',
            'reference': invoice.invoice_number,
            'description': invoice.description or f'Invoice {invoice.invoice_number}',
            'debit': 0.0,
            'credit': round(invoice.total_amount, 2),
        })
        for payment in invoice.payments.all():
            events.append({
                'date': payment.payment_date,
                'type': 'PAYMENT',
                'reference': payment.reference or '',
                'description': f'Payment for {invoice.invoice_number}',
                'debit': round(payment.amount, 2),
                'credit': 0.0,
            })

    events.sort(key=lambda e: (str(e['date']), 0 if e['type'] == 'INVOICE' else 1))

    running_balance = 0.0
    lines = []
    for e in events:
        running_balance += e['credit'] - e['debit']
        lines.append({
            'date': str(e['date']),
            'type': e['type'],
            'reference': e['reference'],
            'description': e['description'],
            'debit': e['debit'],
            'credit': e['credit'],
            'running_balance': round(running_balance, 2),
        })

    return {
        'entity_id': vendor.vendor_id,
        'entity_name': vendor.name,
        'lines': lines,
        'closing_balance': round(running_balance, 2),
    }
```

- [ ] **Step 4: Add the `statement` action and PDF template**

In `backend/payables/views.py`, insert this method into `VendorViewSet` between `destroy` (ends line 77) and the `@action(... url_path='export')` decorator (line 81):

```python
    @action(detail=True, methods=['get'], url_path='statement')
    def statement(self, request, pk=None):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        data = services.get_vendor_statement(pk, company_id)
        if data is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        fmt = request.query_params.get('format', 'json')
        if fmt == 'pdf':
            return pdf_response('payables/vendor_statement.html', data, f'vendor-statement-{pk}')
        if fmt == 'xlsx':
            headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)']
            rows = [
                [l['date'], l['type'], l['reference'], l['description'], l['debit'], l['credit'], l['running_balance']]
                for l in data['lines']
            ]
            rows.append(['', '', '', '', '', 'CLOSING BALANCE', data['closing_balance']])
            return xlsx_response(headers, rows, f'vendor-statement-{pk}', 'Statement')
        return Response(data)
```

`VendorViewSet` currently has no `services` import — confirm `from . import services` is present near the top of `payables/views.py` (it already is, added for `PurchaseInvoiceViewSet`/`ItemViewSet` use).

Create `backend/payables/templates/payables/vendor_statement.html`:

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 11px; margin: 20px; color: #1a1a2e; }
  h1 { font-size: 16px; margin: 0 0 4px; }
  .subtitle { color: #555; margin: 0 0 16px; font-size: 10px; }
  table { width: 100%; border-collapse: collapse; }
  th { background: #1a1a2e; color: white; padding: 6px 8px; text-align: left; font-size: 10px; }
  th:nth-child(5), th:nth-child(6), th:nth-child(7),
  td:nth-child(5), td:nth-child(6), td:nth-child(7) { text-align: right; }
  td { padding: 5px 8px; border-bottom: 1px solid #eee; }
  tr:nth-child(even) td { background: #f9f9fb; }
  tfoot td { font-weight: bold; background: #f0f0f5; border-top: 2px solid #1a1a2e; }
</style>
</head>
<body>
<h1>Vendor Statement</h1>
<p class="subtitle">{{ entity_name }}</p>
<table>
  <thead>
    <tr>
      <th>Date</th><th>Type</th><th>Reference</th><th>Description</th>
      <th>Debit (&#8358;)</th><th>Credit (&#8358;)</th><th>Running Balance (&#8358;)</th>
    </tr>
  </thead>
  <tbody>
    {% for line in lines %}
    <tr>
      <td>{{ line.date }}</td>
      <td>{{ line.type }}</td>
      <td>{{ line.reference }}</td>
      <td>{{ line.description }}</td>
      <td>{{ line.debit|floatformat:2 }}</td>
      <td>{{ line.credit|floatformat:2 }}</td>
      <td>{{ line.running_balance|floatformat:2 }}</td>
    </tr>
    {% endfor %}
  </tbody>
  <tfoot>
    <tr>
      <td colspan="6">Closing Balance</td>
      <td>{{ closing_balance|floatformat:2 }}</td>
    </tr>
  </tfoot>
</table>
</body>
</html>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker exec django_backend python manage.py test payables.tests.VendorStatementTests -v 2`

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/payables/services.py backend/payables/views.py backend/payables/templates/payables/vendor_statement.html backend/payables/tests.py
git commit -m "$(cat <<'EOF'
feat: add vendor statement endpoint with running balance

Computes the ledger from Vendor -> invoices -> payments relationships
directly, not shared GL account lines, so one vendor's balance can't
be blended with another's.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Customer Statement — Backend

**Files:**
- Modify: `backend/receivables/services.py:3` (import), append new function at end (after line 169)
- Modify: `backend/receivables/views.py:69` (insert new action between `destroy` and `export` in `CustomerViewSet`)
- Create: `backend/receivables/templates/receivables/customer_statement.html`
- Test: `backend/receivables/tests.py` (append new `TestCase` class at end of file)

**Interfaces:**
- Produces: `receivables.services.get_customer_statement(customer_id: str, company_id: str) -> dict | None`. Same shape as `get_vendor_statement`'s return value, but `type` values are `'INVOICE' | 'RECEIPT'`.
- Produces: `GET /api/receivables/customers/{id}/statement/` (default JSON), `?format=pdf`, `?format=xlsx`.
- Consumes: existing `Customer.invoices` (`RelationshipFrom(SalesInvoice, 'BILLED_TO')`), `SalesInvoice.receipts` (`RelationshipFrom(ARReceipt, 'RECEIVES_PAYMENT_FOR')`), and `xlsx_response`/`pdf_response` from `config.export_utils`.

- [ ] **Step 1: Write the failing tests**

Open `backend/receivables/tests.py` and append this class at the end of the file:

```python
class CustomerStatementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _post_invoice(self, customer_id, amount, suffix=''):
        ar = self.client.post('/api/accounts/', {
            'name': f'AR Control{suffix}', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json').data
        revenue = self.client.post('/api/accounts/', {
            'name': f'Revenue{suffix}', 'account_type': 'Sales', 'normal_balance': 'CREDIT',
        }, format='json').data
        invoice = self.client.post('/api/receivables/invoices/', {
            'date': '2026-01-01', 'due_date': '2026-02-01',
            'customer_id': customer_id, 'ar_account_id': ar['account_id'],
            'lines': [{'description': 'Line item', 'amount': amount, 'revenue_account_id': revenue['account_id']}],
        }, format='json').data
        return invoice

    def test_statement_running_balance_after_partial_receipt(self):
        import uuid
        customer = self.client.post('/api/receivables/customers/', {'name': 'Test Customer'}, format='json').data
        invoice = self._post_invoice(customer['customer_id'], 1000.0)
        self.client.post(f"/api/receivables/invoices/{invoice['invoice_id']}/post/")

        bank_gl = self.client.post('/api/accounts/', {
            'name': 'Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json').data
        bank = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank', 'bank_name': 'GTBank', 'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 5000.0, 'opening_balance_date': '2026-01-01',
            'gl_account_id_input': bank_gl['account_id'],
        }, format='json').data
        self.client.post(f"/api/receivables/invoices/{invoice['invoice_id']}/receive/", {
            'receipt_date': '2026-01-15', 'amount': 400.0, 'bank_account_id': bank['bank_account_id'],
        }, format='json')

        resp = self.client.get(f"/api/receivables/customers/{customer['customer_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        lines = resp.data['lines']
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['type'], 'INVOICE')
        self.assertEqual(lines[0]['debit'], 1000.0)
        self.assertEqual(lines[0]['credit'], 0.0)
        self.assertEqual(lines[0]['running_balance'], 1000.0)
        self.assertEqual(lines[1]['type'], 'RECEIPT')
        self.assertEqual(lines[1]['credit'], 400.0)
        self.assertEqual(lines[1]['running_balance'], 600.0)
        self.assertEqual(resp.data['closing_balance'], 600.0)

    def test_statement_excludes_draft_invoices(self):
        customer = self.client.post('/api/receivables/customers/', {'name': 'Draft Customer'}, format='json').data
        self._post_invoice(customer['customer_id'], 500.0, suffix=' Draft')  # left unposted (DRAFT)

        resp = self.client.get(f"/api/receivables/customers/{customer['customer_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['lines'], [])
        self.assertEqual(resp.data['closing_balance'], 0.0)

    def test_statement_returns_404_for_unknown_customer(self):
        resp = self.client.get('/api/receivables/customers/does-not-exist/statement/')
        self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker exec django_backend python manage.py test receivables.tests.CustomerStatementTests -v 2`

Expected: `test_statement_running_balance_after_partial_receipt` and `test_statement_excludes_draft_invoices` FAIL with `AssertionError: 404 != 200`. `test_statement_returns_404_for_unknown_customer` PASSes already (same reasoning as Task 1 Step 2).

- [ ] **Step 3: Implement `get_customer_statement`**

In `backend/receivables/services.py`, change the import line at the top:

```python
from .models import SalesInvoice, ARReceipt, Customer
```

Then append this function at the end of the file:

```python
def get_customer_statement(customer_id: str, company_id: str) -> dict | None:
    customer = Customer.nodes.get_or_none(customer_id=customer_id, company_id=company_id)
    if not customer:
        return None

    invoices = [i for i in customer.invoices.all() if i.status in ('POSTED', 'PAID')]

    events = []
    for invoice in invoices:
        events.append({
            'date': invoice.date,
            'type': 'INVOICE',
            'reference': invoice.invoice_number,
            'description': invoice.description or f'Invoice {invoice.invoice_number}',
            'debit': round(invoice.total_amount, 2),
            'credit': 0.0,
        })
        for receipt in invoice.receipts.all():
            events.append({
                'date': receipt.receipt_date,
                'type': 'RECEIPT',
                'reference': receipt.reference or '',
                'description': f'Receipt for {invoice.invoice_number}',
                'debit': 0.0,
                'credit': round(receipt.amount, 2),
            })

    events.sort(key=lambda e: (str(e['date']), 0 if e['type'] == 'INVOICE' else 1))

    running_balance = 0.0
    lines = []
    for e in events:
        running_balance += e['debit'] - e['credit']
        lines.append({
            'date': str(e['date']),
            'type': e['type'],
            'reference': e['reference'],
            'description': e['description'],
            'debit': e['debit'],
            'credit': e['credit'],
            'running_balance': round(running_balance, 2),
        })

    return {
        'entity_id': customer.customer_id,
        'entity_name': customer.name,
        'lines': lines,
        'closing_balance': round(running_balance, 2),
    }
```

- [ ] **Step 4: Add the `statement` action and PDF template**

In `backend/receivables/views.py`, insert this method into `CustomerViewSet` between `destroy` (ends line 68) and the `@action(... url_path='export')` decorator (line 70):

```python
    @action(detail=True, methods=['get'], url_path='statement')
    def statement(self, request, pk=None):
        from config.export_utils import xlsx_response, pdf_response
        company_id = get_active_company_id(request)
        data = services.get_customer_statement(pk, company_id)
        if data is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        fmt = request.query_params.get('format', 'json')
        if fmt == 'pdf':
            return pdf_response('receivables/customer_statement.html', data, f'customer-statement-{pk}')
        if fmt == 'xlsx':
            headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)']
            rows = [
                [l['date'], l['type'], l['reference'], l['description'], l['debit'], l['credit'], l['running_balance']]
                for l in data['lines']
            ]
            rows.append(['', '', '', '', '', 'CLOSING BALANCE', data['closing_balance']])
            return xlsx_response(headers, rows, f'customer-statement-{pk}', 'Statement')
        return Response(data)
```

Create `backend/receivables/templates/receivables/customer_statement.html`:

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 11px; margin: 20px; color: #1a1a2e; }
  h1 { font-size: 16px; margin: 0 0 4px; }
  .subtitle { color: #555; margin: 0 0 16px; font-size: 10px; }
  table { width: 100%; border-collapse: collapse; }
  th { background: #1a1a2e; color: white; padding: 6px 8px; text-align: left; font-size: 10px; }
  th:nth-child(5), th:nth-child(6), th:nth-child(7),
  td:nth-child(5), td:nth-child(6), td:nth-child(7) { text-align: right; }
  td { padding: 5px 8px; border-bottom: 1px solid #eee; }
  tr:nth-child(even) td { background: #f9f9fb; }
  tfoot td { font-weight: bold; background: #f0f0f5; border-top: 2px solid #1a1a2e; }
</style>
</head>
<body>
<h1>Customer Statement</h1>
<p class="subtitle">{{ entity_name }}</p>
<table>
  <thead>
    <tr>
      <th>Date</th><th>Type</th><th>Reference</th><th>Description</th>
      <th>Debit (&#8358;)</th><th>Credit (&#8358;)</th><th>Running Balance (&#8358;)</th>
    </tr>
  </thead>
  <tbody>
    {% for line in lines %}
    <tr>
      <td>{{ line.date }}</td>
      <td>{{ line.type }}</td>
      <td>{{ line.reference }}</td>
      <td>{{ line.description }}</td>
      <td>{{ line.debit|floatformat:2 }}</td>
      <td>{{ line.credit|floatformat:2 }}</td>
      <td>{{ line.running_balance|floatformat:2 }}</td>
    </tr>
    {% endfor %}
  </tbody>
  <tfoot>
    <tr>
      <td colspan="6">Closing Balance</td>
      <td>{{ closing_balance|floatformat:2 }}</td>
    </tr>
  </tfoot>
</table>
</body>
</html>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker exec django_backend python manage.py test receivables.tests.CustomerStatementTests -v 2`

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/receivables/services.py backend/receivables/views.py backend/receivables/templates/receivables/customer_statement.html backend/receivables/tests.py
git commit -m "$(cat <<'EOF'
feat: add customer statement endpoint with running balance

Mirrors the vendor statement endpoint: computes the ledger from
Customer -> invoices -> receipts relationships directly, not shared
GL account lines.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Vendor Statement — Frontend

**Files:**
- Modify: `frontend/sage-frontend/src/app/services/payables.service.ts` (append two methods)
- Test: `frontend/sage-frontend/src/app/services/payables.service.spec.ts` (append one spec)
- Create: `frontend/sage-frontend/src/app/payables/vendor-statement/vendor-statement.component.ts`
- Create: `frontend/sage-frontend/src/app/payables/vendor-statement/vendor-statement.component.html`
- Modify: `frontend/sage-frontend/src/app/app.routes.ts:90` (add route after the `payables/vendors` line)
- Modify: `frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.html:73-82` (add Statement button)

**Interfaces:**
- Consumes: `GET /api/payables/vendors/{id}/statement/` from Task 1, returning `{entity_id, entity_name, lines: [{date, type, reference, description, debit, credit, running_balance}], closing_balance}`.
- Produces: `PayablesService.getVendorStatement(id: string): Promise<any>`, `PayablesService.exportVendorStatement(id: string, format: 'pdf' | 'xlsx'): Promise<void>`.
- Produces: route `/payables/vendors/:id` rendering `VendorStatementComponent`.

- [ ] **Step 1: Write the failing spec for the export method**

In `frontend/sage-frontend/src/app/services/payables.service.spec.ts`, add a second `it` block inside the existing `describe('PayablesService', ...)`, right after the closing `});` of the first `it`:

```typescript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend/sage-frontend && npm test -- --watch=false --include='**/payables.service.spec.ts'`

Expected: FAIL with `TypeError: (intermediate value).exportVendorStatement is not a function` (or Angular CLI's equivalent "not a function" error).

- [ ] **Step 3: Add the service methods**

In `frontend/sage-frontend/src/app/services/payables.service.ts`, append these two methods right after `exportVendors` (before the closing `}` of the class):

```typescript
  getVendorStatement(id: string) { return axios.get(this.base + `vendors/${id}/statement/`).then(r => r.data); }

  async exportVendorStatement(id: string, format: 'pdf' | 'xlsx'): Promise<void> {
    const response = await axios.get(this.base + `vendors/${id}/statement/`, {
      params: { format },
      responseType: 'blob',
    });
    const blob = new Blob([response.data], { type: response.headers['content-type'] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vendor-statement.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend/sage-frontend && npm test -- --watch=false --include='**/payables.service.spec.ts'`

Expected: both specs in `PayablesService` PASS.

- [ ] **Step 5: Create the statement component**

Create `frontend/sage-frontend/src/app/payables/vendor-statement/vendor-statement.component.ts`:

```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { PayablesService } from '../../services/payables.service';

@Component({
  selector: 'app-vendor-statement',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './vendor-statement.component.html',
})
export class VendorStatementComponent implements OnInit {
  statement: any = null;
  loading = true;
  error = '';

  private id = '';

  constructor(private route: ActivatedRoute, private payables: PayablesService) {}

  async ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    try {
      this.statement = await this.payables.getVendorStatement(this.id);
    } catch {
      this.error = 'Failed to load vendor statement.';
    } finally {
      this.loading = false;
    }
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      await this.payables.exportVendorStatement(this.id, format);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
```

Create `frontend/sage-frontend/src/app/payables/vendor-statement/vendor-statement.component.html`:

```html
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
  <div>
    <a routerLink="/payables/vendors" style="font-size:.85rem;color:#555;text-decoration:none">&larr; Back to Vendors</a>
    <h2 style="margin:.35rem 0 0">{{ statement?.entity_name }}</h2>
  </div>
  @if (statement) {
    <div style="display:flex;gap:.5rem">
      <button (click)="exportFile('pdf')"
        style="background:white;color:#555;padding:.5rem 1rem;border:1px solid #ccc;border-radius:4px;cursor:pointer;font-size:.875rem">
        Export PDF
      </button>
      <button (click)="exportFile('xlsx')"
        style="background:white;color:#555;padding:.5rem 1rem;border:1px solid #ccc;border-radius:4px;cursor:pointer;font-size:.875rem">
        Export XLSX
      </button>
    </div>
  }
</div>

@if (loading) { <p>Loading…</p> }
@if (error) { <p style="color:red">{{ error }}</p> }
@if (!loading && !error && statement) {
  <div style="background:white;border-radius:8px;padding:1rem 1.25rem;margin-bottom:1rem;box-shadow:0 1px 4px rgba(0,0,0,.1)">
    <span style="color:#555;font-size:.875rem">Amount Owed</span>
    <div style="font-size:1.5rem;font-weight:700"
      [style.color]="statement.closing_balance > 0 ? '#b42318' : 'inherit'">
      ₦{{ statement.closing_balance | number:'1.2-2' }}
    </div>
  </div>
  <div style="background:white;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1)">
    <table style="width:100%;border-collapse:collapse">
      <thead style="background:#f0f0f5">
        <tr>
          <th style="text-align:left;padding:.75rem 1rem">Date</th>
          <th style="text-align:left;padding:.75rem 1rem">Type</th>
          <th style="text-align:left;padding:.75rem 1rem">Reference</th>
          <th style="text-align:left;padding:.75rem 1rem">Description</th>
          <th style="text-align:right;padding:.75rem 1rem">Debit</th>
          <th style="text-align:right;padding:.75rem 1rem">Credit</th>
          <th style="text-align:right;padding:.75rem 1rem">Running Balance</th>
        </tr>
      </thead>
      <tbody>
        @for (line of statement.lines; track $index) {
          <tr style="border-top:1px solid #eee">
            <td style="padding:.75rem 1rem">{{ line.date }}</td>
            <td style="padding:.75rem 1rem">{{ line.type }}</td>
            <td style="padding:.75rem 1rem">{{ line.reference }}</td>
            <td style="padding:.75rem 1rem">{{ line.description }}</td>
            <td style="padding:.75rem 1rem;text-align:right">{{ line.debit ? ('₦' + (line.debit | number:'1.2-2')) : '' }}</td>
            <td style="padding:.75rem 1rem;text-align:right">{{ line.credit ? ('₦' + (line.credit | number:'1.2-2')) : '' }}</td>
            <td style="padding:.75rem 1rem;text-align:right;font-weight:600">₦{{ line.running_balance | number:'1.2-2' }}</td>
          </tr>
        } @empty {
          <tr>
            <td colspan="7" style="padding:2.5rem;text-align:center;color:var(--text-muted)">
              No transactions yet.
            </td>
          </tr>
        }
      </tbody>
    </table>
  </div>
}
```

- [ ] **Step 6: Add the route**

In `frontend/sage-frontend/src/app/app.routes.ts`, change line 90 from:

```typescript
      { path: 'payables/vendors', loadComponent: () => import('./payables/vendor-list/vendor-list.component').then(m => m.VendorListComponent) },
```

to:

```typescript
      { path: 'payables/vendors', loadComponent: () => import('./payables/vendor-list/vendor-list.component').then(m => m.VendorListComponent) },
      { path: 'payables/vendors/:id', loadComponent: () => import('./payables/vendor-statement/vendor-statement.component').then(m => m.VendorStatementComponent) },
```

- [ ] **Step 7: Add the Statement button to the vendor list**

In `frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.ts`, change the import block at the top from:

```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { PayablesService } from '../../services/payables.service';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';
```

to:

```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { PayablesService } from '../../services/payables.service';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';
```

Then change the `@Component` decorator's `imports` array from:

```typescript
  imports: [CommonModule, ReactiveFormsModule, PaginatePipe, PaginationComponent],
```

to:

```typescript
  imports: [CommonModule, ReactiveFormsModule, RouterModule, PaginatePipe, PaginationComponent],
```

In `frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.html`, change the actions cell (lines 73-82) from:

```html
            <td style="padding:.75rem 1rem;text-align:right">
              <button (click)="startEdit(vendor)"
                style="margin-right:.5rem;padding:.35rem .75rem;background:none;border:1px solid #ccc;border-radius:4px;cursor:pointer">
                Edit
              </button>
              <button (click)="deleteVendor(vendor)"
                style="padding:.35rem .75rem;background:#fff1f2;color:#b42318;border:1px solid #fecdca;border-radius:4px;cursor:pointer">
                Delete
              </button>
            </td>
```

to:

```html
            <td style="padding:.75rem 1rem;text-align:right">
              <a [routerLink]="['/payables/vendors', vendor.vendor_id]"
                style="margin-right:.5rem;padding:.35rem .75rem;background:none;border:1px solid #ccc;border-radius:4px;cursor:pointer;text-decoration:none;color:inherit;display:inline-block">
                Statement
              </a>
              <button (click)="startEdit(vendor)"
                style="margin-right:.5rem;padding:.35rem .75rem;background:none;border:1px solid #ccc;border-radius:4px;cursor:pointer">
                Edit
              </button>
              <button (click)="deleteVendor(vendor)"
                style="padding:.35rem .75rem;background:#fff1f2;color:#b42318;border:1px solid #fecdca;border-radius:4px;cursor:pointer">
                Delete
              </button>
            </td>
```

- [ ] **Step 8: Manually verify in the browser**

Run: `docker-compose up -d` (if not already running), then open `http://localhost:4200/payables/vendors`.

Expected: each vendor row shows a "Statement" link; clicking it navigates to `/payables/vendors/:id` and shows the vendor's name, closing balance, and a ledger table (or "No transactions yet." if the vendor has no posted invoices). Export PDF/XLSX buttons trigger a file download.

- [ ] **Step 9: Commit**

```bash
git add frontend/sage-frontend/src/app/services/payables.service.ts frontend/sage-frontend/src/app/services/payables.service.spec.ts frontend/sage-frontend/src/app/payables/vendor-statement/ frontend/sage-frontend/src/app/app.routes.ts frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.ts frontend/sage-frontend/src/app/payables/vendor-list/vendor-list.component.html
git commit -m "$(cat <<'EOF'
feat: add vendor statement page with running balance ledger

Adds a Statement link per vendor row that opens a new /payables/vendors/:id
page rendering the vendor's invoice/payment history with a running
balance, plus PDF/XLSX export.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Customer Statement — Frontend

**Files:**
- Modify: `frontend/sage-frontend/src/app/services/receivables.service.ts` (append two methods)
- Test: `frontend/sage-frontend/src/app/services/receivables.service.spec.ts` (append one spec)
- Create: `frontend/sage-frontend/src/app/receivables/customer-statement/customer-statement.component.ts`
- Create: `frontend/sage-frontend/src/app/receivables/customer-statement/customer-statement.component.html`
- Modify: `frontend/sage-frontend/src/app/app.routes.ts:96` (add route after the `receivables/customers` line)
- Modify: `frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.html:83-92` (add Statement button)

**Interfaces:**
- Consumes: `GET /api/receivables/customers/{id}/statement/` from Task 2, returning `{entity_id, entity_name, lines: [{date, type, reference, description, debit, credit, running_balance}], closing_balance}`.
- Produces: `ReceivablesService.getCustomerStatement(id: string): Promise<any>`, `ReceivablesService.exportCustomerStatement(id: string, format: 'pdf' | 'xlsx'): Promise<void>`.
- Produces: route `/receivables/customers/:id` rendering `CustomerStatementComponent`.

- [ ] **Step 1: Write the failing spec for the export method**

In `frontend/sage-frontend/src/app/services/receivables.service.spec.ts`, add a second `it` block inside the existing `describe('ReceivablesService', ...)`, right after the closing `});` of the first `it`:

```typescript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend/sage-frontend && npm test -- --watch=false --include='**/receivables.service.spec.ts'`

Expected: FAIL with `TypeError: (intermediate value).exportCustomerStatement is not a function` (or Angular CLI's equivalent "not a function" error).

- [ ] **Step 3: Add the service methods**

In `frontend/sage-frontend/src/app/services/receivables.service.ts`, append these two methods right after `exportInvoices` (before the closing `}` of the class):

```typescript
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend/sage-frontend && npm test -- --watch=false --include='**/receivables.service.spec.ts'`

Expected: both specs in `ReceivablesService` PASS.

- [ ] **Step 5: Create the statement component**

Create `frontend/sage-frontend/src/app/receivables/customer-statement/customer-statement.component.ts`:

```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { ReceivablesService } from '../../services/receivables.service';

@Component({
  selector: 'app-customer-statement',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './customer-statement.component.html',
})
export class CustomerStatementComponent implements OnInit {
  statement: any = null;
  loading = true;
  error = '';

  private id = '';

  constructor(private route: ActivatedRoute, private receivables: ReceivablesService) {}

  async ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    try {
      this.statement = await this.receivables.getCustomerStatement(this.id);
    } catch {
      this.error = 'Failed to load customer statement.';
    } finally {
      this.loading = false;
    }
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      await this.receivables.exportCustomerStatement(this.id, format);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
```

Create `frontend/sage-frontend/src/app/receivables/customer-statement/customer-statement.component.html`:

```html
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
  <div>
    <a routerLink="/receivables/customers" style="font-size:.85rem;color:#555;text-decoration:none">&larr; Back to Customers</a>
    <h2 style="margin:.35rem 0 0">{{ statement?.entity_name }}</h2>
  </div>
  @if (statement) {
    <div style="display:flex;gap:.5rem">
      <button (click)="exportFile('pdf')"
        style="background:white;color:#555;padding:.5rem 1rem;border:1px solid #ccc;border-radius:4px;cursor:pointer;font-size:.875rem">
        Export PDF
      </button>
      <button (click)="exportFile('xlsx')"
        style="background:white;color:#555;padding:.5rem 1rem;border:1px solid #ccc;border-radius:4px;cursor:pointer;font-size:.875rem">
        Export XLSX
      </button>
    </div>
  }
</div>

@if (loading) { <p>Loading…</p> }
@if (error) { <p style="color:red">{{ error }}</p> }
@if (!loading && !error && statement) {
  <div style="background:white;border-radius:8px;padding:1rem 1.25rem;margin-bottom:1rem;box-shadow:0 1px 4px rgba(0,0,0,.1)">
    <span style="color:#555;font-size:.875rem">Amount Owed to Us</span>
    <div style="font-size:1.5rem;font-weight:700"
      [style.color]="statement.closing_balance > 0 ? '#b42318' : 'inherit'">
      ₦{{ statement.closing_balance | number:'1.2-2' }}
    </div>
  </div>
  <div style="background:white;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1)">
    <table style="width:100%;border-collapse:collapse">
      <thead style="background:#f0f0f5">
        <tr>
          <th style="text-align:left;padding:.75rem 1rem">Date</th>
          <th style="text-align:left;padding:.75rem 1rem">Type</th>
          <th style="text-align:left;padding:.75rem 1rem">Reference</th>
          <th style="text-align:left;padding:.75rem 1rem">Description</th>
          <th style="text-align:right;padding:.75rem 1rem">Debit</th>
          <th style="text-align:right;padding:.75rem 1rem">Credit</th>
          <th style="text-align:right;padding:.75rem 1rem">Running Balance</th>
        </tr>
      </thead>
      <tbody>
        @for (line of statement.lines; track $index) {
          <tr style="border-top:1px solid #eee">
            <td style="padding:.75rem 1rem">{{ line.date }}</td>
            <td style="padding:.75rem 1rem">{{ line.type }}</td>
            <td style="padding:.75rem 1rem">{{ line.reference }}</td>
            <td style="padding:.75rem 1rem">{{ line.description }}</td>
            <td style="padding:.75rem 1rem;text-align:right">{{ line.debit ? ('₦' + (line.debit | number:'1.2-2')) : '' }}</td>
            <td style="padding:.75rem 1rem;text-align:right">{{ line.credit ? ('₦' + (line.credit | number:'1.2-2')) : '' }}</td>
            <td style="padding:.75rem 1rem;text-align:right;font-weight:600">₦{{ line.running_balance | number:'1.2-2' }}</td>
          </tr>
        } @empty {
          <tr>
            <td colspan="7" style="padding:2.5rem;text-align:center;color:var(--text-muted)">
              No transactions yet.
            </td>
          </tr>
        }
      </tbody>
    </table>
  </div>
}
```

- [ ] **Step 6: Add the route**

In `frontend/sage-frontend/src/app/app.routes.ts`, change line 96 from:

```typescript
      { path: 'receivables/customers', loadComponent: () => import('./receivables/customer-list/customer-list.component').then(m => m.CustomerListComponent) },
```

to:

```typescript
      { path: 'receivables/customers', loadComponent: () => import('./receivables/customer-list/customer-list.component').then(m => m.CustomerListComponent) },
      { path: 'receivables/customers/:id', loadComponent: () => import('./receivables/customer-statement/customer-statement.component').then(m => m.CustomerStatementComponent) },
```

- [ ] **Step 7: Add the Statement button to the customer list**

In `frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.ts`, change the import block at the top from:

```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ReceivablesService } from '../../services/receivables.service';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';
```

to:

```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { ReceivablesService } from '../../services/receivables.service';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';
```

Then change the `@Component` decorator's `imports` array from:

```typescript
  imports: [CommonModule, ReactiveFormsModule, PaginatePipe, PaginationComponent],
```

to:

```typescript
  imports: [CommonModule, ReactiveFormsModule, RouterModule, PaginatePipe, PaginationComponent],
```

In `frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.html`, change the actions cell (lines 83-92) from:

```html
            <td style="padding:.75rem 1rem;text-align:right">
              <button (click)="startEdit(customer)"
                style="margin-right:.5rem;padding:.35rem .75rem;background:none;border:1px solid #ccc;border-radius:4px;cursor:pointer">
                Edit
              </button>
              <button (click)="deleteCustomer(customer)"
                style="padding:.35rem .75rem;background:#fff1f2;color:#b42318;border:1px solid #fecdca;border-radius:4px;cursor:pointer">
                Delete
              </button>
            </td>
```

to:

```html
            <td style="padding:.75rem 1rem;text-align:right">
              <a [routerLink]="['/receivables/customers', customer.customer_id]"
                style="margin-right:.5rem;padding:.35rem .75rem;background:none;border:1px solid #ccc;border-radius:4px;cursor:pointer;text-decoration:none;color:inherit;display:inline-block">
                Statement
              </a>
              <button (click)="startEdit(customer)"
                style="margin-right:.5rem;padding:.35rem .75rem;background:none;border:1px solid #ccc;border-radius:4px;cursor:pointer">
                Edit
              </button>
              <button (click)="deleteCustomer(customer)"
                style="padding:.35rem .75rem;background:#fff1f2;color:#b42318;border:1px solid #fecdca;border-radius:4px;cursor:pointer">
                Delete
              </button>
            </td>
```

- [ ] **Step 8: Manually verify in the browser**

Run: `docker-compose up -d` (if not already running), then open `http://localhost:4200/receivables/customers`.

Expected: each customer row shows a "Statement" link; clicking it navigates to `/receivables/customers/:id` and shows the customer's name, outstanding balance, and a ledger table (or "No transactions yet." if the customer has no posted invoices). Export PDF/XLSX buttons trigger a file download.

- [ ] **Step 9: Commit**

```bash
git add frontend/sage-frontend/src/app/services/receivables.service.ts frontend/sage-frontend/src/app/services/receivables.service.spec.ts frontend/sage-frontend/src/app/receivables/customer-statement/ frontend/sage-frontend/src/app/app.routes.ts frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.ts frontend/sage-frontend/src/app/receivables/customer-list/customer-list.component.html
git commit -m "$(cat <<'EOF'
feat: add customer statement page with running balance ledger

Adds a Statement link per customer row that opens a new
/receivables/customers/:id page rendering the customer's invoice/receipt
history with a running balance, plus PDF/XLSX export.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
