# Company Name on PDF/XLSX Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every PDF and XLSX export in both the Django backend and the Electron desktop app shows the name of the company whose books it belongs to.

**Architecture:** `Company.name` is already embedded in the JWT on both platforms, so new accessor functions read it off the request with zero DB lookups. Two shared render functions per platform (`pdf_response`/`xlsx_response` in Django, `sendPdf`/`sendTablePdf`/`sendXlsx` in the desktop app) inject a letterhead automatically; every export call site is updated to pass the request/company name through.

**Tech Stack:** Django + WeasyPrint + openpyxl (backend); Express + pdfmake + ExcelJS (desktop, TypeScript).

## Global Constraints

- No new dependencies — WeasyPrint, openpyxl, pdfmake, and ExcelJS are already in use.
- No `Company` model changes (name-only letterhead; no address/logo).
- No Angular changes — the frontend only downloads blobs the backend already generates.
- Existing export API routes, filenames, and content types are unchanged.
- Letterhead typography: serif fallback stack `Georgia, "Times New Roman", serif` (backend), Helvetica-Bold at larger size (desktop pdfmake, which has no other font registered) — no Google Fonts network dependency, per the approved design spec.
- XLSX header shape: row 1 = company name (bold, 14pt, merged across all data columns), row 2 = report/sheet title (bold, 11pt, merged), row 3 = blank, row 4 = existing bolded column headers.
- Reference spec: `docs/superpowers/specs/2026-07-17-company-name-on-exports-design.md`.

---

## Task 1: Backend — `get_active_company_name` accessor

**Files:**
- Modify: `backend/config/auth.py`
- Test: `backend/config/tests.py` (new file)

**Interfaces:**
- Produces: `get_active_company_name(request) -> str | None`, mirroring the existing `get_active_company_id`.

- [ ] **Step 1: Write the failing test**

Create `backend/config/tests.py`:

```python
from unittest.mock import Mock
from django.test import TestCase


class GetActiveCompanyNameTests(TestCase):
    def test_returns_company_name_from_validated_jwt(self):
        from config.auth import get_active_company_name
        request = Mock()
        request.auth = {'company_id': 'c1', 'company_name': 'Topfaith University', 'role': 'Admin'}
        self.assertEqual(get_active_company_name(request), 'Topfaith University')

    def test_returns_none_when_request_has_no_auth(self):
        from config.auth import get_active_company_name
        request = Mock()
        request.auth = None
        self.assertIsNone(get_active_company_name(request))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python manage.py test config -v 2`
Expected: FAIL — `ImportError: cannot import name 'get_active_company_name'`

- [ ] **Step 3: Add the accessor**

In `backend/config/auth.py`, add after `get_active_company_id`:

```python
def get_active_company_name(request):
    """Returns the active company_name claim from the validated JWT, or None
    for a pre-company token. Mirrors get_active_company_id."""
    auth = getattr(request, 'auth', None)
    if auth is None:
        return None
    return auth.get('company_name')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && python manage.py test config -v 2`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/config/auth.py backend/config/tests.py
git commit -m "feat: add get_active_company_name request accessor"
```

---

## Task 2: Backend — template DIRS setting + shared letterhead partial

**Files:**
- Modify: `backend/config/settings.py`
- Create: `backend/config/templates/shared/_pdf_letterhead.html`

**Interfaces:**
- Produces: a template includable as `{% include "shared/_pdf_letterhead.html" %}` from any app template, rendering `{{ company_name }}` if present.

- [ ] **Step 1: Add the templates DIRS entry**

In `backend/config/settings.py`, the `TEMPLATES` setting currently reads:

```python
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
```

Change `'DIRS': []` to:

```python
        'DIRS': [BASE_DIR / 'config' / 'templates'],
```

- [ ] **Step 2: Create the letterhead partial**

Create `backend/config/templates/shared/_pdf_letterhead.html`:

```html
{% if company_name %}
<div style="font-family: Georgia, 'Times New Roman', serif; font-size: 17px; font-weight: 700; color: #1a1a2e; margin-bottom: 6px;">{{ company_name }}</div>
<div style="border-bottom: 1px solid #1a1a2e; margin-bottom: 14px;"></div>
{% endif %}
```

- [ ] **Step 3: Verify Django can find it**

Run: `cd backend && source venv/bin/activate && python manage.py shell -c "from django.template.loader import get_template; get_template('shared/_pdf_letterhead.html'); print('OK')"`
Expected: `OK` (no `TemplateDoesNotExist`)

- [ ] **Step 4: Commit**

```bash
git add backend/config/settings.py backend/config/templates/shared/_pdf_letterhead.html
git commit -m "feat: add shared PDF letterhead partial and templates dir"
```

---

## Task 3: Backend — `pdf_response`/`xlsx_response` company-name injection

**Files:**
- Modify: `backend/config/export_utils.py`
- Modify: `backend/config/tests.py`

**Interfaces:**
- Consumes: `get_active_company_name(request)` from Task 1.
- Produces: `pdf_response(request, template_name, context, filename)` — new first `request` param; injects `company_name` into the template context. `xlsx_response(request, headers, rows, filename, sheet_title='Export')` — new first `request` param; writes a company-name/title header above the data. `write_xlsx_header(ws, company_name, title, num_cols) -> int` — helper used by Task 10's report-specific workbook builders too; returns the number of header rows written (3).

- [ ] **Step 1: Write the failing tests**

Replace the contents of `backend/config/tests.py` with (keeping Task 1's tests and adding new ones):

```python
import io
from unittest.mock import Mock, patch
from django.test import TestCase
from openpyxl import load_workbook


class GetActiveCompanyNameTests(TestCase):
    def test_returns_company_name_from_validated_jwt(self):
        from config.auth import get_active_company_name
        request = Mock()
        request.auth = {'company_id': 'c1', 'company_name': 'Topfaith University', 'role': 'Admin'}
        self.assertEqual(get_active_company_name(request), 'Topfaith University')

    def test_returns_none_when_request_has_no_auth(self):
        from config.auth import get_active_company_name
        request = Mock()
        request.auth = None
        self.assertIsNone(get_active_company_name(request))


def _request_with_company(company_name):
    request = Mock()
    request.auth = {'company_id': 'c1', 'company_name': company_name, 'role': 'Admin'}
    return request


class XlsxResponseCompanyHeaderTests(TestCase):
    def test_writes_company_name_and_title_above_headers(self):
        from config.export_utils import xlsx_response
        request = _request_with_company('Topfaith University')
        response = xlsx_response(request, ['Code', 'Name'], [['001', 'Cash']], 'accounts', 'Accounts')
        wb = load_workbook(io.BytesIO(response.content))
        ws = wb.active
        self.assertEqual(ws['A1'].value, 'Topfaith University')
        self.assertEqual(ws['A2'].value, 'Accounts')
        self.assertEqual([c.value for c in ws[4]], ['Code', 'Name'])
        self.assertEqual([c.value for c in ws[5]], ['001', 'Cash'])

    def test_blank_company_name_does_not_error(self):
        from config.export_utils import xlsx_response
        request = _request_with_company(None)
        response = xlsx_response(request, ['Code'], [['001']], 'accounts', 'Accounts')
        wb = load_workbook(io.BytesIO(response.content))
        ws = wb.active
        self.assertEqual(ws['A1'].value, '')
        self.assertEqual([c.value for c in ws[4]], ['Code'])


class PdfResponseCompanyContextTests(TestCase):
    @patch('weasyprint.HTML')
    @patch('django.template.loader.render_to_string')
    def test_injects_company_name_into_template_context(self, mock_render, mock_html):
        from config.export_utils import pdf_response
        mock_render.return_value = '<html></html>'
        mock_html.return_value.write_pdf.return_value = b'%PDF-1.4'
        request = _request_with_company('Topfaith University')

        pdf_response(request, 'accounts/account_list.html', {'rows': []}, 'accounts')

        context = mock_render.call_args.args[1]
        self.assertEqual(context['company_name'], 'Topfaith University')
        self.assertEqual(context['rows'], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python manage.py test config -v 2`
Expected: FAIL — `TypeError: xlsx_response() missing 1 required positional argument` (current signature has no `request`)

- [ ] **Step 3: Rewrite `export_utils.py`**

Replace the full contents of `backend/config/export_utils.py`:

```python
import io
import csv
from django.http import HttpResponse
from config.auth import get_active_company_name


def write_xlsx_header(ws, company_name, title, num_cols):
    """Writes a merged company-name row (bold, 14pt) and title row (bold,
    11pt) above the data, followed by a blank row. Returns the number of
    rows written, so callers building a worksheet manually know the offset
    before appending their own header/data rows."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    last_col = get_column_letter(max(num_cols, 1))
    ws.append([company_name or ''])
    ws.merge_cells(f'A1:{last_col}1')
    ws['A1'].font = Font(bold=True, size=14)
    ws.append([title])
    ws.merge_cells(f'A2:{last_col}2')
    ws['A2'].font = Font(bold=True, size=11)
    ws.append([])
    return 3


def xlsx_response(request, headers, rows, filename, sheet_title='Export'):
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    write_xlsx_header(ws, get_active_company_name(request), sheet_title, len(headers))
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    return response


def pdf_response(request, template_name, context, filename):
    from django.template.loader import render_to_string
    from weasyprint import HTML
    html = render_to_string(template_name, {**context, 'company_name': get_active_company_name(request)})
    pdf = HTML(string=html).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}.pdf"'
    return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python manage.py test config -v 2`
Expected: PASS (6 tests) — note this will still fail at this point because every call site in `accounts/views.py`, `banks/views.py`, etc. calls the old two-arg/four-arg signatures. That breakage is expected and fixed in Tasks 4–11. Confirm specifically that the `config` test module itself passes in isolation; ignore failures from other apps' test modules at this step.

- [ ] **Step 5: Commit**

```bash
git add backend/config/export_utils.py backend/config/tests.py
git commit -m "feat: inject company name into pdf_response/xlsx_response"
```

---

## Task 4: Backend — accounts app export + template

**Files:**
- Modify: `backend/accounts/views.py:84-87`
- Modify: `backend/accounts/templates/accounts/account_list.html`

**Interfaces:**
- Consumes: `pdf_response(request, ...)` / `xlsx_response(request, ...)` from Task 3; `shared/_pdf_letterhead.html` from Task 2.

- [ ] **Step 1: Pass `request` into the export call site**

In `backend/accounts/views.py`, inside `AccountViewSet.export`, replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['code', 'name', 'account_type', 'normal_balance', 'balance'], r)) for r in rows]}
            return pdf_response('accounts/account_list.html', ctx, 'accounts')
        return xlsx_response(headers, rows, 'accounts', 'Accounts')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['code', 'name', 'account_type', 'normal_balance', 'balance'], r)) for r in rows]}
            return pdf_response(request, 'accounts/account_list.html', ctx, 'accounts')
        return xlsx_response(request, headers, rows, 'accounts', 'Accounts')
```

- [ ] **Step 2: Add the letterhead include to the template**

In `backend/accounts/templates/accounts/account_list.html`, replace:

```html
<body>
<h1>Chart of Accounts</h1>
```

with:

```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Chart of Accounts</h1>
```

- [ ] **Step 3: Run the app's test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test accounts config -v 2`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/accounts/views.py backend/accounts/templates/accounts/account_list.html
git commit -m "feat: show company name on accounts export"
```

---

## Task 5: Backend — banks app export + template

**Files:**
- Modify: `backend/banks/views.py:82-87`
- Modify: `backend/banks/templates/banks/bank_account_list.html`

- [ ] **Step 1: Pass `request` into the export call site**

In `backend/banks/views.py`, inside `BankAccountViewSet.export`, replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'bank_name', 'account_number', 'opening_balance', 'current_balance'], r
            )) for r in rows]}
            return pdf_response('banks/bank_account_list.html', ctx, 'bank-accounts')
        return xlsx_response(headers, rows, 'bank-accounts', 'Bank Accounts')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'bank_name', 'account_number', 'opening_balance', 'current_balance'], r
            )) for r in rows]}
            return pdf_response(request, 'banks/bank_account_list.html', ctx, 'bank-accounts')
        return xlsx_response(request, headers, rows, 'bank-accounts', 'Bank Accounts')
```

- [ ] **Step 2: Add the letterhead include to the template**

In `backend/banks/templates/banks/bank_account_list.html`, replace:

```html
<body>
<h1>Bank Accounts</h1>
```

with:

```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Bank Accounts</h1>
```

- [ ] **Step 3: Run the app's test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test banks config -v 2`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/banks/views.py backend/banks/templates/banks/bank_account_list.html
git commit -m "feat: show company name on bank accounts export"
```

---

## Task 6: Backend — budget app export + template

**Files:**
- Modify: `backend/budget/views.py:67-72`
- Modify: `backend/budget/templates/budget/budget_list.html`

- [ ] **Step 1: Pass `request` into the export call site**

In `backend/budget/views.py`, inside the budget `export` action, replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'fiscal_year', 'total_budgeted', 'status', 'created_by'], r
            )) for r in rows]}
            return pdf_response('budget/budget_list.html', ctx, 'budgets')
        return xlsx_response(headers, rows, 'budgets', 'Budgets')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'fiscal_year', 'total_budgeted', 'status', 'created_by'], r
            )) for r in rows]}
            return pdf_response(request, 'budget/budget_list.html', ctx, 'budgets')
        return xlsx_response(request, headers, rows, 'budgets', 'Budgets')
```

- [ ] **Step 2: Add the letterhead include to the template**

In `backend/budget/templates/budget/budget_list.html`, replace:

```html
<body>
<h1>Budgets</h1>
```

with:

```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Budgets</h1>
```

- [ ] **Step 3: Run the app's test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test budget config -v 2`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/budget/views.py backend/budget/templates/budget/budget_list.html
git commit -m "feat: show company name on budgets export"
```

---

## Task 7: Backend — journals app export + template

**Files:**
- Modify: `backend/journals/views.py:108-113`
- Modify: `backend/journals/templates/journals/entry_list.html`

- [ ] **Step 1: Pass `request` into the export call site**

In `backend/journals/views.py`, inside `JournalEntryViewSet.export`, replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['reference', 'date', 'description', 'total_debit', 'total_credit', 'status'], r
            )) for r in rows]}
            return pdf_response('journals/entry_list.html', ctx, 'journal-entries')
        return xlsx_response(headers, rows, 'journal-entries', 'Journal Entries')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['reference', 'date', 'description', 'total_debit', 'total_credit', 'status'], r
            )) for r in rows]}
            return pdf_response(request, 'journals/entry_list.html', ctx, 'journal-entries')
        return xlsx_response(request, headers, rows, 'journal-entries', 'Journal Entries')
```

- [ ] **Step 2: Add the letterhead include to the template**

In `backend/journals/templates/journals/entry_list.html`, replace:

```html
<body>
<h1>Journal Entries</h1>
```

with:

```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Journal Entries</h1>
```

- [ ] **Step 3: Run the app's test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test journals config -v 2`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/journals/views.py backend/journals/templates/journals/entry_list.html
git commit -m "feat: show company name on journal entries export"
```

---

## Task 8: Backend — payables app exports + templates

**Files:**
- Modify: `backend/payables/views.py` (vendor `statement` action ~L92-107, vendor `export` action ~L112-121, invoice `export` action ~L231-249, item `export` action ~L318-332)
- Modify: `backend/payables/templates/payables/vendor_list.html`
- Modify: `backend/payables/templates/payables/vendor_statement.html`
- Modify: `backend/payables/templates/payables/invoice_list.html`
- Modify: `backend/payables/templates/payables/item_list.html`

- [ ] **Step 1: Vendor statement — pass `request`**

In `backend/payables/views.py`, inside `VendorViewSet.statement`, replace:

```python
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
```

with:

```python
        if fmt == 'pdf':
            return pdf_response(request, 'payables/vendor_statement.html', data, f'vendor-statement-{pk}')
        if fmt == 'xlsx':
            headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)']
            rows = [
                [l['date'], l['type'], l['reference'], l['description'], l['debit'], l['credit'], l['running_balance']]
                for l in data['lines']
            ]
            rows.append(['', '', '', '', '', 'CLOSING BALANCE', data['closing_balance']])
            return xlsx_response(request, headers, rows, f'vendor-statement-{pk}', 'Statement')
```

- [ ] **Step 2: Vendor export — pass `request`**

Replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['name', 'email', 'phone', 'address'], r)) for r in rows]}
            return pdf_response('payables/vendor_list.html', ctx, 'vendors')
        return xlsx_response(headers, rows, 'vendors', 'Vendors')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['name', 'email', 'phone', 'address'], r)) for r in rows]}
            return pdf_response(request, 'payables/vendor_list.html', ctx, 'vendors')
        return xlsx_response(request, headers, rows, 'vendors', 'Vendors')
```

- [ ] **Step 3: Purchase invoice export — pass `request`**

Replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['invoice_number', 'vendor', 'date', 'due_date', 'total_amount', 'amount_paid', 'status'], r
            )) for r in rows]}
            return pdf_response('payables/invoice_list.html', ctx, 'purchase-invoices')
        return xlsx_response(headers, rows, 'purchase-invoices', 'Purchase Invoices')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['invoice_number', 'vendor', 'date', 'due_date', 'total_amount', 'amount_paid', 'status'], r
            )) for r in rows]}
            return pdf_response(request, 'payables/invoice_list.html', ctx, 'purchase-invoices')
        return xlsx_response(request, headers, rows, 'purchase-invoices', 'Purchase Invoices')
```

- [ ] **Step 4: Item export — pass `request`**

Replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'item_type', 'vendor', 'cost_price', 'selling_price'], r
            )) for r in rows]}
            return pdf_response('payables/item_list.html', ctx, 'items')
        return xlsx_response(headers, rows, 'items', 'Items')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['name', 'item_type', 'vendor', 'cost_price', 'selling_price'], r
            )) for r in rows]}
            return pdf_response(request, 'payables/item_list.html', ctx, 'items')
        return xlsx_response(request, headers, rows, 'items', 'Items')
```

- [ ] **Step 5: Add the letterhead include to the four templates**

In `backend/payables/templates/payables/vendor_list.html`, replace:
```html
<body>
<h1>Vendors</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Vendors</h1>
```

In `backend/payables/templates/payables/vendor_statement.html`, replace:
```html
<body>
<h1>Vendor Statement</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Vendor Statement</h1>
```

In `backend/payables/templates/payables/invoice_list.html`, replace:
```html
<body>
<h1>Purchase Invoices</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Purchase Invoices</h1>
```

In `backend/payables/templates/payables/item_list.html`, replace:
```html
<body>
<h1>Items</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Items</h1>
```

- [ ] **Step 6: Run the app's test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test payables config -v 2`
Expected: PASS (the existing `PurchaseInvoicePrintTests` mocked test is fixed in Task 11, not here — it is expected to still fail until then; confirm no *other* payables tests regress)

- [ ] **Step 7: Commit**

```bash
git add backend/payables/views.py backend/payables/templates/payables/vendor_list.html backend/payables/templates/payables/vendor_statement.html backend/payables/templates/payables/invoice_list.html backend/payables/templates/payables/item_list.html
git commit -m "feat: show company name on payables exports and statement"
```

---

## Task 9: Backend — receivables app exports + templates

**Files:**
- Modify: `backend/receivables/views.py` (customer `statement` action ~L81-96, customer `export` action ~L101-110, sales invoice `export` action ~L220-238)
- Modify: `backend/receivables/templates/receivables/customer_list.html`
- Modify: `backend/receivables/templates/receivables/customer_statement.html`
- Modify: `backend/receivables/templates/receivables/invoice_list.html`

- [ ] **Step 1: Customer statement — pass `request`**

In `backend/receivables/views.py`, inside `CustomerViewSet.statement`, replace:

```python
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
```

with:

```python
        if fmt == 'pdf':
            return pdf_response(request, 'receivables/customer_statement.html', data, f'customer-statement-{pk}')
        if fmt == 'xlsx':
            headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)']
            rows = [
                [l['date'], l['type'], l['reference'], l['description'], l['debit'], l['credit'], l['running_balance']]
                for l in data['lines']
            ]
            rows.append(['', '', '', '', '', 'CLOSING BALANCE', data['closing_balance']])
            return xlsx_response(request, headers, rows, f'customer-statement-{pk}', 'Statement')
```

- [ ] **Step 2: Customer export — pass `request`**

Replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['name', 'customer_type', 'email', 'phone'], r)) for r in rows]}
            return pdf_response('receivables/customer_list.html', ctx, 'customers')
        return xlsx_response(headers, rows, 'customers', 'Customers')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(['name', 'customer_type', 'email', 'phone'], r)) for r in rows]}
            return pdf_response(request, 'receivables/customer_list.html', ctx, 'customers')
        return xlsx_response(request, headers, rows, 'customers', 'Customers')
```

- [ ] **Step 3: Sales invoice export — pass `request`**

Replace:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['invoice_number', 'customer', 'date', 'due_date', 'total_amount', 'amount_received', 'status'], r
            )) for r in rows]}
            return pdf_response('receivables/invoice_list.html', ctx, 'sales-invoices')
        return xlsx_response(headers, rows, 'sales-invoices', 'Sales Invoices')
```

with:

```python
        if fmt == 'pdf':
            ctx = {'rows': [dict(zip(
                ['invoice_number', 'customer', 'date', 'due_date', 'total_amount', 'amount_received', 'status'], r
            )) for r in rows]}
            return pdf_response(request, 'receivables/invoice_list.html', ctx, 'sales-invoices')
        return xlsx_response(request, headers, rows, 'sales-invoices', 'Sales Invoices')
```

- [ ] **Step 4: Add the letterhead include to the three templates**

In `backend/receivables/templates/receivables/customer_list.html`, replace:
```html
<body>
<h1>Customers</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Customers</h1>
```

In `backend/receivables/templates/receivables/customer_statement.html`, replace:
```html
<body>
<h1>Customer Statement</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Customer Statement</h1>
```

In `backend/receivables/templates/receivables/invoice_list.html`, replace:
```html
<body>
<h1>Sales Invoices</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Sales Invoices</h1>
```

- [ ] **Step 5: Run the app's test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test receivables config -v 2`
Expected: PASS (the existing `SalesInvoicePrintTests` mocked test is fixed in Task 11, not here)

- [ ] **Step 6: Commit**

```bash
git add backend/receivables/views.py backend/receivables/templates/receivables/customer_list.html backend/receivables/templates/receivables/customer_statement.html backend/receivables/templates/receivables/invoice_list.html
git commit -m "feat: show company name on receivables exports and statement"
```

---

## Task 10: Backend — reports app: dedupe into shared helpers + letterheads

**Files:**
- Modify: `backend/reports/views.py`
- Modify: `backend/reports/templates/reports/trial_balance.html`
- Modify: `backend/reports/templates/reports/income_statement.html`
- Modify: `backend/reports/templates/reports/balance_sheet.html`
- Modify: `backend/reports/templates/reports/gl_detail.html`

**Interfaces:**
- Consumes: `pdf_response`, `xlsx_response` from `config.export_utils` (Task 3) — replaces `reports/views.py`'s own `_pdf_response`/`_xlsx_response`, which used raw `Workbook` objects with no company-name row. All four report `xlsx` branches are rewritten to build a flat `headers`/`rows` pair (the same shape every other app already uses) instead of appending directly to a `Workbook`.

- [ ] **Step 1: Remove the local `_pdf_response`/`_xlsx_response` and import the shared ones**

In `backend/reports/views.py`, replace the top of the file:

```python
import io
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from config.auth import get_active_company_id
from . import services


def _parse_date(value: str, param_name: str):
    from datetime import date
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _pdf_response(template_name, context, filename):
    from django.template.loader import render_to_string
    from weasyprint import HTML
    html = render_to_string(template_name, context)
    pdf = HTML(string=html).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def _xlsx_response(wb, filename):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
```

with:

```python
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from config.auth import get_active_company_id
from config.export_utils import pdf_response, xlsx_response
from . import services


def _parse_date(value: str, param_name: str):
    from datetime import date
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
```

- [ ] **Step 2: Rewrite `trial_balance`'s export branches**

Replace:

```python
    if fmt == 'pdf':
        pdf_rows = []
        for r in rows:
            d = max(0.0, r['total_debits'] - r['total_credits'])
            c = max(0.0, r['total_credits'] - r['total_debits'])
            pdf_rows.append({**r, 'display_debit': round(d, 2), 'display_credit': round(c, 2)})
        pdf_ctx = {
            'rows': pdf_rows,
            'date_from': date_from,
            'date_to': date_to,
            'total_debits': round(sum(r['display_debit'] for r in pdf_rows), 2),
            'total_credits': round(sum(r['display_credit'] for r in pdf_rows), 2),
        }
        return _pdf_response('reports/trial_balance.html', pdf_ctx, f'trial-balance-{date_from}-{date_to}.pdf')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = 'Trial Balance'
        ws.append(['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for r in rows:
            d = max(0.0, r['total_debits'] - r['total_credits'])
            c = max(0.0, r['total_credits'] - r['total_debits'])
            ws.append([r['code'], r['name'], r['account_type'],
                       round(d, 2) if d > 0 else None,
                       round(c, 2) if c > 0 else None])
        total_d = round(sum(max(0.0, r['total_debits'] - r['total_credits']) for r in rows), 2)
        total_c = round(sum(max(0.0, r['total_credits'] - r['total_debits']) for r in rows), 2)
        ws.append(['', 'TOTALS', '', total_d, total_c])
        return _xlsx_response(wb, f'trial-balance-{date_from}-{date_to}.xlsx')
    return JsonResponse(ctx)
```

with:

```python
    if fmt == 'pdf':
        pdf_rows = []
        for r in rows:
            d = max(0.0, r['total_debits'] - r['total_credits'])
            c = max(0.0, r['total_credits'] - r['total_debits'])
            pdf_rows.append({**r, 'display_debit': round(d, 2), 'display_credit': round(c, 2)})
        pdf_ctx = {
            'rows': pdf_rows,
            'date_from': date_from,
            'date_to': date_to,
            'total_debits': round(sum(r['display_debit'] for r in pdf_rows), 2),
            'total_credits': round(sum(r['display_credit'] for r in pdf_rows), 2),
        }
        return pdf_response(request, 'reports/trial_balance.html', pdf_ctx, f'trial-balance-{date_from}-{date_to}')
    if fmt == 'xlsx':
        headers = ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)']
        xlsx_rows = []
        for r in rows:
            d = max(0.0, r['total_debits'] - r['total_credits'])
            c = max(0.0, r['total_credits'] - r['total_debits'])
            xlsx_rows.append([r['code'], r['name'], r['account_type'],
                               round(d, 2) if d > 0 else None,
                               round(c, 2) if c > 0 else None])
        total_d = round(sum(max(0.0, r['total_debits'] - r['total_credits']) for r in rows), 2)
        total_c = round(sum(max(0.0, r['total_credits'] - r['total_debits']) for r in rows), 2)
        xlsx_rows.append(['', 'TOTALS', '', total_d, total_c])
        return xlsx_response(request, headers, xlsx_rows, f'trial-balance-{date_from}-{date_to}', 'Trial Balance')
    return JsonResponse(ctx)
```

- [ ] **Step 3: Rewrite `income_statement`'s export branches**

Replace:

```python
    if fmt == 'pdf':
        return _pdf_response('reports/income_statement.html', data, f'income-statement-{date_from}-{date_to}.pdf')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = 'Income Statement'
        ws.append(['Account', 'Type', 'Amount (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.append(['REVENUE', '', ''])
        for r in data['revenue']:
            ws.append([r['name'], r['account_type'], r['balance']])
        ws.append(['Total Revenue', '', data['total_revenue']])
        ws.append(['COST OF SALES', '', ''])
        for r in data['cost_of_sales']:
            ws.append([r['name'], r['account_type'], r['balance']])
        ws.append(['Gross Profit', '', data['gross_profit']])
        ws.append(['EXPENSES', '', ''])
        for r in data['expenses']:
            ws.append([r['name'], r['account_type'], r['balance']])
        ws.append(['Total Expenses', '', data['total_expenses']])
        ws.append(['Net Surplus / (Deficit)', '', data['net_surplus']])
        return _xlsx_response(wb, f'income-statement-{date_from}-{date_to}.xlsx')
    return JsonResponse(data)
```

with:

```python
    if fmt == 'pdf':
        return pdf_response(request, 'reports/income_statement.html', data, f'income-statement-{date_from}-{date_to}')
    if fmt == 'xlsx':
        headers = ['Account', 'Type', 'Amount (N)']
        xlsx_rows = [['REVENUE', '', '']]
        xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in data['revenue']]
        xlsx_rows.append(['Total Revenue', '', data['total_revenue']])
        xlsx_rows.append(['COST OF SALES', '', ''])
        xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in data['cost_of_sales']]
        xlsx_rows.append(['Gross Profit', '', data['gross_profit']])
        xlsx_rows.append(['EXPENSES', '', ''])
        xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in data['expenses']]
        xlsx_rows.append(['Total Expenses', '', data['total_expenses']])
        xlsx_rows.append(['Net Surplus / (Deficit)', '', data['net_surplus']])
        return xlsx_response(request, headers, xlsx_rows, f'income-statement-{date_from}-{date_to}', 'Income Statement')
    return JsonResponse(data)
```

- [ ] **Step 4: Rewrite `balance_sheet`'s export branches**

Replace:

```python
    if fmt == 'pdf':
        return _pdf_response('reports/balance_sheet.html', data, f'balance-sheet-{as_of_date}.pdf')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = 'Balance Sheet'
        ws.append(['Account', 'Type', 'Balance (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for section_label, items, total_key in [
            ('ASSETS', data['assets'], 'total_assets'),
            ('LIABILITIES', data['liabilities'], 'total_liabilities'),
            ('EQUITY', data['equity'], 'total_equity'),
        ]:
            ws.append([section_label, '', ''])
            for r in items:
                ws.append([r['name'], r['account_type'], r['balance']])
            ws.append([f'Total {section_label.title()}', '', data[total_key]])
        return _xlsx_response(wb, f'balance-sheet-{as_of_date}.xlsx')
    return JsonResponse(data)
```

with:

```python
    if fmt == 'pdf':
        return pdf_response(request, 'reports/balance_sheet.html', data, f'balance-sheet-{as_of_date}')
    if fmt == 'xlsx':
        headers = ['Account', 'Type', 'Balance (N)']
        xlsx_rows = []
        for section_label, items, total_key in [
            ('ASSETS', data['assets'], 'total_assets'),
            ('LIABILITIES', data['liabilities'], 'total_liabilities'),
            ('EQUITY', data['equity'], 'total_equity'),
        ]:
            xlsx_rows.append([section_label, '', ''])
            xlsx_rows += [[r['name'], r['account_type'], r['balance']] for r in items]
            xlsx_rows.append([f'Total {section_label.title()}', '', data[total_key]])
        return xlsx_response(request, headers, xlsx_rows, f'balance-sheet-{as_of_date}', 'Balance Sheet')
    return JsonResponse(data)
```

- [ ] **Step 5: Rewrite `gl_detail`'s export branches**

Replace:

```python
    if fmt == 'pdf':
        return _pdf_response(
            'reports/gl_detail.html', data,
            f'gl-detail-{data["account_code"]}-{date_from}-{date_to}.pdf'
        )
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = f'GL {data["account_code"]}'
        ws.append(['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for line in data['lines']:
            ws.append([line['date'], line['reference'], line['entry_description'],
                       line['entry_type'] or 'MANUAL', line['side'], line['amount'], line['running_balance']])
        ws.append(['', '', '', '', 'CLOSING BALANCE', '', data['closing_balance']])
        return _xlsx_response(wb, f'gl-detail-{data["account_code"]}-{date_from}-{date_to}.xlsx')
    return JsonResponse(data)
```

with:

```python
    if fmt == 'pdf':
        return pdf_response(
            request, 'reports/gl_detail.html', data,
            f'gl-detail-{data["account_code"]}-{date_from}-{date_to}'
        )
    if fmt == 'xlsx':
        headers = ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)']
        xlsx_rows = [
            [line['date'], line['reference'], line['entry_description'],
             line['entry_type'] or 'MANUAL', line['side'], line['amount'], line['running_balance']]
            for line in data['lines']
        ]
        xlsx_rows.append(['', '', '', '', 'CLOSING BALANCE', '', data['closing_balance']])
        return xlsx_response(
            request, headers, xlsx_rows,
            f'gl-detail-{data["account_code"]}-{date_from}-{date_to}', f'GL {data["account_code"]}'
        )
    return JsonResponse(data)
```

- [ ] **Step 6: Add the letterhead include to the four report templates**

In `backend/reports/templates/reports/trial_balance.html`, replace:
```html
<body>
<h1>Trial Balance</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Trial Balance</h1>
```

In `backend/reports/templates/reports/income_statement.html`, replace:
```html
<body>
<h1>Income Statement</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Income Statement</h1>
```

In `backend/reports/templates/reports/balance_sheet.html`, replace:
```html
<body>
<h1>Balance Sheet</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>Balance Sheet</h1>
```

In `backend/reports/templates/reports/gl_detail.html`, replace:
```html
<body>
<h1>General Ledger Detail</h1>
```
with:
```html
<body>
{% include "shared/_pdf_letterhead.html" %}
<h1>General Ledger Detail</h1>
```

- [ ] **Step 7: Run the app's test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test reports config -v 2`
Expected: PASS — `BalanceSheetPLTests` and `DashboardAssetsTests` only exercise the `json` format path (`fmt` defaults to `'json'`), so they are unaffected by the `pdf`/`xlsx` branch rewrite.

- [ ] **Step 8: Commit**

```bash
git add backend/reports/views.py backend/reports/templates/reports/trial_balance.html backend/reports/templates/reports/income_statement.html backend/reports/templates/reports/balance_sheet.html backend/reports/templates/reports/gl_detail.html
git commit -m "refactor: dedupe reports exports onto shared pdf/xlsx helpers with company letterhead"
```

---

## Task 11: Backend — invoice documents (sales/purchase) + existing test fixes

**Files:**
- Modify: `backend/receivables/templates/receivables/sales_invoice.html`
- Modify: `backend/payables/templates/payables/purchase_invoice.html`
- Modify: `backend/receivables/views.py:146-152` (`SalesInvoiceViewSet.print_invoice`)
- Modify: `backend/payables/views.py:157-163` (`PurchaseInvoiceViewSet.print_invoice`)
- Modify: `backend/receivables/tests.py:16-35`
- Modify: `backend/payables/tests.py:16-35`

**Interfaces:**
- These two templates keep their own distinct theme (`#1f4e79`) and do **not** use `shared/_pdf_letterhead.html` (that partial is styled for the `#1a1a2e` list/report theme) — they get one inline-styled line matching their own header block instead.

- [ ] **Step 1: Add the company name line to the sales invoice template**

In `backend/receivables/templates/receivables/sales_invoice.html`, replace:

```html
  <header class="header">
    <h1>Sales Invoice</h1>
    <div class="invoice-number">Invoice #{{ invoice.invoice_number }}</div>
  </header>
```

with:

```html
  <header class="header">
    {% if company_name %}<div style="font-size: 12px; letter-spacing: 0.5px; text-transform: uppercase; color: #52606d; margin-bottom: 4px;">{{ company_name }}</div>{% endif %}
    <h1>Sales Invoice</h1>
    <div class="invoice-number">Invoice #{{ invoice.invoice_number }}</div>
  </header>
```

- [ ] **Step 2: Add the company name line to the purchase invoice template**

In `backend/payables/templates/payables/purchase_invoice.html`, replace:

```html
  <header class="header">
    <h1>Purchase Invoice</h1>
    <div class="invoice-number">Invoice #{{ invoice.invoice_number }}</div>
  </header>
```

with:

```html
  <header class="header">
    {% if company_name %}<div style="font-size: 12px; letter-spacing: 0.5px; text-transform: uppercase; color: #52606d; margin-bottom: 4px;">{{ company_name }}</div>{% endif %}
    <h1>Purchase Invoice</h1>
    <div class="invoice-number">Invoice #{{ invoice.invoice_number }}</div>
  </header>
```

- [ ] **Step 3: Pass `request` in `SalesInvoiceViewSet.print_invoice`**

In `backend/receivables/views.py`, replace:

```python
        return pdf_response('receivables/sales_invoice.html', {
            'invoice': invoice,
            'customer': customer,
            'lines': lines,
            'settled_amount': invoice.amount_received,
            'outstanding_amount': max(0, invoice.total_amount - invoice.amount_received),
        }, f'sales-invoice-{invoice.invoice_number}')
```

with:

```python
        return pdf_response(request, 'receivables/sales_invoice.html', {
            'invoice': invoice,
            'customer': customer,
            'lines': lines,
            'settled_amount': invoice.amount_received,
            'outstanding_amount': max(0, invoice.total_amount - invoice.amount_received),
        }, f'sales-invoice-{invoice.invoice_number}')
```

- [ ] **Step 4: Pass `request` in `PurchaseInvoiceViewSet.print_invoice`**

In `backend/payables/views.py`, replace:

```python
        return pdf_response('payables/purchase_invoice.html', {
            'invoice': invoice,
            'vendor': vendor,
            'lines': lines,
            'settled_amount': invoice.amount_paid,
            'outstanding_amount': max(0, invoice.total_amount - invoice.amount_paid),
        }, f'purchase-invoice-{invoice.invoice_number}')
```

with:

```python
        return pdf_response(request, 'payables/purchase_invoice.html', {
            'invoice': invoice,
            'vendor': vendor,
            'lines': lines,
            'settled_amount': invoice.amount_paid,
            'outstanding_amount': max(0, invoice.total_amount - invoice.amount_paid),
        }, f'purchase-invoice-{invoice.invoice_number}')
```

- [ ] **Step 5: Fix the existing mocked-`pdf_response` test in `receivables/tests.py`**

The mocked `pdf_response` now receives `request` as its first positional arg, shifting every subsequent index by one. Replace:

```python
        self.assertEqual(response.status_code, 200)
        pdf_response.assert_called_once()
        self.assertEqual(pdf_response.call_args.args[0], 'receivables/sales_invoice.html')
        self.assertEqual(pdf_response.call_args.args[2], 'sales-invoice-SI-0001')
        self.assertEqual(pdf_response.call_args.args[1]['outstanding_amount'], 1300.0)
```

with:

```python
        self.assertEqual(response.status_code, 200)
        pdf_response.assert_called_once()
        self.assertEqual(pdf_response.call_args.args[1], 'receivables/sales_invoice.html')
        self.assertEqual(pdf_response.call_args.args[3], 'sales-invoice-SI-0001')
        self.assertEqual(pdf_response.call_args.args[2]['outstanding_amount'], 1300.0)
```

- [ ] **Step 6: Fix the existing mocked-`pdf_response` test in `payables/tests.py`**

Replace:

```python
        self.assertEqual(response.status_code, 200)
        pdf_response.assert_called_once()
        self.assertEqual(pdf_response.call_args.args[0], 'payables/purchase_invoice.html')
        self.assertEqual(pdf_response.call_args.args[2], 'purchase-invoice-PI-0001')
        self.assertEqual(pdf_response.call_args.args[1]['outstanding_amount'], 1300.0)
```

with:

```python
        self.assertEqual(response.status_code, 200)
        pdf_response.assert_called_once()
        self.assertEqual(pdf_response.call_args.args[1], 'payables/purchase_invoice.html')
        self.assertEqual(pdf_response.call_args.args[3], 'purchase-invoice-PI-0001')
        self.assertEqual(pdf_response.call_args.args[2]['outstanding_amount'], 1300.0)
```

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && source venv/bin/activate && python manage.py test`
Expected: PASS — this is the first point where every app's tests run together after Tasks 1–11; this is the true regression gate for the whole backend half of the plan.

- [ ] **Step 8: Commit**

```bash
git add backend/receivables/templates/receivables/sales_invoice.html backend/payables/templates/payables/purchase_invoice.html backend/receivables/views.py backend/payables/views.py backend/receivables/tests.py backend/payables/tests.py
git commit -m "feat: show company name on invoice documents; fix pdf_response signature in tests"
```

---

## Task 12: Desktop — `getActiveCompanyName` accessor

**Files:**
- Modify: `desktop/page_desktop/src/server/lib/rbac.ts`

**Interfaces:**
- Produces: `getActiveCompanyName(req: Request): string | null`, mirroring `getActiveCompanyId`.

- [ ] **Step 1: Add the accessor**

In `desktop/page_desktop/src/server/lib/rbac.ts`, replace:

```typescript
export function getActiveCompanyId(req: Request): string | null {
  return req.auth?.company_id ?? null;
}
```

with:

```typescript
export function getActiveCompanyId(req: Request): string | null {
  return req.auth?.company_id ?? null;
}

export function getActiveCompanyName(req: Request): string | null {
  return req.auth?.company_name ?? null;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd desktop/page_desktop && npm run typecheck`
Expected: PASS (no errors)

- [ ] **Step 3: Commit**

```bash
git add desktop/page_desktop/src/server/lib/rbac.ts
git commit -m "feat: add getActiveCompanyName request accessor"
```

---

## Task 13: Desktop — letterhead support in `sendPdf`/`sendTablePdf`/`sendXlsx`

**Files:**
- Modify: `desktop/page_desktop/src/server/exports/pdf.ts`
- Modify: `desktop/page_desktop/src/server/exports/xlsx.ts`

**Interfaces:**
- Produces: `sendPdf(res, filename, docDefinition, companyName?: string | null)`, `sendTablePdf(res, filename, title, headers, rows, companyName?: string | null)`, `sendXlsx(res, filename, sheetName, headers, rows, companyName?: string | null)` — all with a new optional trailing param (default `null`) so this task alone does not break any existing call site; Tasks 14–18 pass the real value through.

- [ ] **Step 1: Rewrite `exports/pdf.ts`**

Replace the full contents of `desktop/page_desktop/src/server/exports/pdf.ts`:

```typescript
import PdfPrinter from 'pdfmake/src/printer';
import { Response } from 'express';

const FONTS = {
  Helvetica: { normal: 'Helvetica', bold: 'Helvetica-Bold', italics: 'Helvetica-Oblique', bolditalics: 'Helvetica-BoldOblique' },
};

/** Letterhead content prepended to every export — bold company name plus a
 * thin rule, mirroring the backend's shared/_pdf_letterhead.html partial.
 * pdfmake has no other font registered, so brand consistency here comes
 * from color/weight/spacing rather than an exact typeface match. */
function letterheadContent(companyName: string | null | undefined): any[] {
  if (!companyName) return [];
  return [
    { text: companyName, style: 'letterhead' },
    { canvas: [{ type: 'line', x1: 0, y1: 0, x2: 535, y2: 0, lineWidth: 1, lineColor: '#1a1a2e' }], margin: [0, 2, 0, 10] },
  ];
}

/** Renders a pdfmake document definition to a buffer and streams it inline —
 * mirrors the live app's weasyprint pdf_response() (PRD §4.16/§8): inline
 * Content-Disposition, same intent (view in-browser, not force-download). */
export function sendPdf(res: Response, filename: string, docDefinition: any, companyName: string | null = null): void {
  const printer = new PdfPrinter(FONTS);
  const doc = printer.createPdfKitDocument({
    defaultStyle: { font: 'Helvetica', fontSize: 9 },
    pageMargins: [30, 30, 30, 30],
    ...docDefinition,
    content: [...letterheadContent(companyName), ...docDefinition.content],
    styles: { letterhead: { fontSize: 16, bold: true, color: '#1a1a2e' }, ...docDefinition.styles },
  });
  const chunks: Buffer[] = [];
  doc.on('data', (c: Buffer) => chunks.push(c));
  doc.on('end', () => {
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `inline; filename="${filename}.pdf"`);
    res.send(Buffer.concat(chunks));
  });
  doc.end();
}

/** Generic bolded-header table PDF for list exports (accounts, vendors,
 * customers, items, invoices, journal entries, budgets, bank accounts). */
export function sendTablePdf(res: Response, filename: string, title: string, headers: string[], rows: (string | number | null)[][], companyName: string | null = null): void {
  sendPdf(res, filename, {
    content: [
      { text: title, style: 'title' },
      {
        table: {
          headerRows: 1,
          widths: headers.map(() => 'auto'),
          body: [headers.map((h) => ({ text: h, bold: true })), ...rows.map((r) => r.map((v) => String(v ?? '')))],
        },
      },
    ],
    styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
  }, companyName);
}
```

- [ ] **Step 2: Rewrite `exports/xlsx.ts`**

Replace the full contents of `desktop/page_desktop/src/server/exports/xlsx.ts`:

```typescript
import ExcelJS from 'exceljs';
import { Response } from 'express';

/** Writes a merged company-name row (bold, 14pt) and title row (bold, 11pt)
 * above the data, followed by a blank row — mirrors the backend's
 * write_xlsx_header() in config/export_utils.py. */
function writeCompanyHeader(ws: ExcelJS.Worksheet, companyName: string | null | undefined, title: string, numCols: number): void {
  const lastCol = Math.max(numCols, 1);
  const nameRow = ws.addRow([companyName ?? '']);
  ws.mergeCells(1, 1, 1, lastCol);
  nameRow.font = { bold: true, size: 14 };
  const titleRow = ws.addRow([title]);
  ws.mergeCells(2, 1, 2, lastCol);
  titleRow.font = { bold: true, size: 11 };
  ws.addRow([]);
}

/** Mirrors the live app's openpyxl exports: a bolded header row, one sheet,
 * attachment download (PRD §8/CLAUDE.md's "same bolded-header-row output shape"). */
export async function sendXlsx(
  res: Response,
  filename: string,
  sheetName: string,
  headers: string[],
  rows: (string | number | null)[][],
  companyName: string | null = null,
): Promise<void> {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet(sheetName);
  writeCompanyHeader(ws, companyName, sheetName, headers.length);
  const headerRow = ws.addRow(headers);
  headerRow.font = { bold: true };
  for (const row of rows) ws.addRow(row);
  ws.columns.forEach((col) => {
    col.width = 18;
  });
  const buffer = await wb.xlsx.writeBuffer();
  res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}.xlsx"`);
  res.send(Buffer.from(buffer));
}
```

- [ ] **Step 3: Typecheck**

Run: `cd desktop/page_desktop && npm run typecheck`
Expected: PASS — every existing call site omits the new optional `companyName` param, which is valid TypeScript since it defaults to `null`.

- [ ] **Step 4: Commit**

```bash
git add desktop/page_desktop/src/server/exports/pdf.ts desktop/page_desktop/src/server/exports/xlsx.ts
git commit -m "feat: add company-name letterhead to desktop pdf/xlsx export helpers"
```

---

## Task 14: Desktop — wire company name through accounts, budget, journals routes

**Files:**
- Modify: `desktop/page_desktop/src/server/routes/accounts.ts:11-12,46-57`
- Modify: `desktop/page_desktop/src/server/routes/budget.ts:7-9,48-65`
- Modify: `desktop/page_desktop/src/server/routes/journals.ts:7,11-12,64-80`

- [ ] **Step 1: `accounts.ts` — import and use `getActiveCompanyName`**

Replace the import line:

```typescript
import { getActiveCompanyId } from '../lib/rbac';
```

with:

```typescript
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
```

Then replace the `/export/` handler:

```typescript
  router.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('accounts').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('code').execute();
    const headers = ['Code', 'Name', 'Type', 'Normal Balance', 'Balance (N)'];
    const dataRows = await Promise.all(rows.map(async (a) => [a.code, a.name, a.account_type, a.normal_balance, await computeAccountBalance(db, a.account_id)]));
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'accounts', 'Chart of Accounts', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'accounts', 'Accounts', headers, dataRows);
  });
```

with:

```typescript
  router.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('accounts').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('code').execute();
    const headers = ['Code', 'Name', 'Type', 'Normal Balance', 'Balance (N)'];
    const dataRows = await Promise.all(rows.map(async (a) => [a.code, a.name, a.account_type, a.normal_balance, await computeAccountBalance(db, a.account_id)]));
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'accounts', 'Chart of Accounts', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'accounts', 'Accounts', headers, dataRows, companyName);
  });
```

- [ ] **Step 2: `budget.ts` — import and use `getActiveCompanyName`**

Replace the import line:

```typescript
import { getActiveCompanyId } from '../lib/rbac';
```

with:

```typescript
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
```

Then replace the `/export/` handler:

```typescript
  budgets.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('budgets').selectAll().where('company_id', '=', companyId ?? '').orderBy('created_at', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (b) => {
        const lines = await db.selectFrom('budget_lines').select('budgeted_amount').where('budget_id', '=', b.budget_id).execute();
        const total = lines.reduce((s, l) => s + l.budgeted_amount, 0);
        return [b.name, b.fiscal_year, total, b.status, b.created_by];
      }),
    );
    const headers = ['Name', 'Fiscal Year', 'Total Budgeted (N)', 'Status', 'Created By'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'budgets', 'Budgets', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'budgets', 'Budgets', headers, dataRows);
  });
```

with:

```typescript
  budgets.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('budgets').selectAll().where('company_id', '=', companyId ?? '').orderBy('created_at', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (b) => {
        const lines = await db.selectFrom('budget_lines').select('budgeted_amount').where('budget_id', '=', b.budget_id).execute();
        const total = lines.reduce((s, l) => s + l.budgeted_amount, 0);
        return [b.name, b.fiscal_year, total, b.status, b.created_by];
      }),
    );
    const headers = ['Name', 'Fiscal Year', 'Total Budgeted (N)', 'Status', 'Created By'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'budgets', 'Budgets', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'budgets', 'Budgets', headers, dataRows, companyName);
  });
```

- [ ] **Step 3: `journals.ts` — import and use `getActiveCompanyName`**

Replace the import line:

```typescript
import { getActiveCompanyId } from '../lib/rbac';
```

with:

```typescript
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
```

Then replace the `/export/` handler:

```typescript
  entries.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db
      .selectFrom('journal_entries')
      .selectAll()
      .where('company_id', '=', companyId ?? '')
      .orderBy('date', 'desc')
      .execute();
    const headers = ['Reference', 'Date', 'Description', 'Debit (N)', 'Credit (N)', 'Status'];
    const dataRows = rows.map((e) => [e.reference, e.date, e.description, e.total_debit, e.total_credit, e.status]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'journal-entries', 'Journal Entries', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'journal-entries', 'Journal Entries', headers, dataRows);
  });
```

with:

```typescript
  entries.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db
      .selectFrom('journal_entries')
      .selectAll()
      .where('company_id', '=', companyId ?? '')
      .orderBy('date', 'desc')
      .execute();
    const headers = ['Reference', 'Date', 'Description', 'Debit (N)', 'Credit (N)', 'Status'];
    const dataRows = rows.map((e) => [e.reference, e.date, e.description, e.total_debit, e.total_credit, e.status]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'journal-entries', 'Journal Entries', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'journal-entries', 'Journal Entries', headers, dataRows, companyName);
  });
```

Note: `journals.ts` also does `import { userHasAnyGroup } from '../lib/rbac';` on a separate line — leave that import untouched.

- [ ] **Step 4: Typecheck**

Run: `cd desktop/page_desktop && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/page_desktop/src/server/routes/accounts.ts desktop/page_desktop/src/server/routes/budget.ts desktop/page_desktop/src/server/routes/journals.ts
git commit -m "feat: show company name on desktop accounts, budgets, journal entries exports"
```

---

## Task 15: Desktop — wire company name through banks routes

**Files:**
- Modify: `desktop/page_desktop/src/server/routes/banks.ts:9,89-101,363-383`

- [ ] **Step 1: Import `getActiveCompanyName`**

Replace:

```typescript
import { getActiveCompanyId } from '../lib/rbac';
```

with:

```typescript
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
```

- [ ] **Step 2: Bank accounts export**

Replace:

```typescript
  accounts.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('bank_accounts').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const serialized = await Promise.all(rows.map((r) => serializeBankAccount(db, r)));
    const headers = ['Name', 'Bank', 'Account No.', 'Opening Balance (N)', 'Current Balance (N)'];
    const dataRows = serialized.map((r) => [r.name, r.bank_name, r.account_number, r.opening_balance, r.current_balance]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'bank-accounts', 'Bank Accounts', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'bank-accounts', 'Bank Accounts', headers, dataRows);
  });
```

with:

```typescript
  accounts.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('bank_accounts').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const serialized = await Promise.all(rows.map((r) => serializeBankAccount(db, r)));
    const headers = ['Name', 'Bank', 'Account No.', 'Opening Balance (N)', 'Current Balance (N)'];
    const dataRows = serialized.map((r) => [r.name, r.bank_name, r.account_number, r.opening_balance, r.current_balance]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'bank-accounts', 'Bank Accounts', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'bank-accounts', 'Bank Accounts', headers, dataRows, companyName);
  });
```

- [ ] **Step 3: Bank transactions export (xlsx only — CSV branch unaffected)**

Replace:

```typescript
  transactions.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const rows = await queryTransactions(
      companyId,
      (req.query.bank_account_id as string) || undefined,
      (req.query.date_from as string) || undefined,
      (req.query.date_to as string) || undefined,
    );
    const serialized = await Promise.all(rows.map((r) => serializeTransaction(db, r)));
    const headers = ['Reference', 'Date', 'Bank', 'Type', 'Description', 'Amount'];
    const dataRows = serialized.map((r) => [r.reference, r.date, r.source_bank_name ?? '', r.transaction_type, r.description ?? '', r.amount]);
    const fmt = (req.query.format as string) || 'csv';
    if (fmt === 'xlsx') {
      await sendXlsx(res, 'bank-transactions', 'Bank Transactions', headers, dataRows);
      return;
    }
```

with:

```typescript
  transactions.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const companyName = getActiveCompanyName(req);
    const rows = await queryTransactions(
      companyId,
      (req.query.bank_account_id as string) || undefined,
      (req.query.date_from as string) || undefined,
      (req.query.date_to as string) || undefined,
    );
    const serialized = await Promise.all(rows.map((r) => serializeTransaction(db, r)));
    const headers = ['Reference', 'Date', 'Bank', 'Type', 'Description', 'Amount'];
    const dataRows = serialized.map((r) => [r.reference, r.date, r.source_bank_name ?? '', r.transaction_type, r.description ?? '', r.amount]);
    const fmt = (req.query.format as string) || 'csv';
    if (fmt === 'xlsx') {
      await sendXlsx(res, 'bank-transactions', 'Bank Transactions', headers, dataRows, companyName);
      return;
    }
```

- [ ] **Step 4: Typecheck**

Run: `cd desktop/page_desktop && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/page_desktop/src/server/routes/banks.ts
git commit -m "feat: show company name on desktop bank accounts and transactions exports"
```

---

## Task 16: Desktop — wire company name through payables routes

**Files:**
- Modify: `desktop/page_desktop/src/server/routes/payables.ts:7,89-100,102-138,208-224,236-263,441-457`

- [ ] **Step 1: Import `getActiveCompanyName`**

Replace:

```typescript
import { getActiveCompanyId } from '../lib/rbac';
```

with:

```typescript
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
```

- [ ] **Step 2: Vendor export**

Replace:

```typescript
  vendors.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('vendors').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const headers = ['Name', 'Email', 'Phone', 'Address'];
    const dataRows = rows.map((v) => [v.name, v.email, v.phone, v.address]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'vendors', 'Vendors', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'vendors', 'Vendors', headers, dataRows);
  });
```

with:

```typescript
  vendors.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('vendors').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const headers = ['Name', 'Email', 'Phone', 'Address'];
    const dataRows = rows.map((v) => [v.name, v.email, v.phone, v.address]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'vendors', 'Vendors', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'vendors', 'Vendors', headers, dataRows, companyName);
  });
```

- [ ] **Step 3: Vendor statement**

Replace:

```typescript
  vendors.get('/:id/statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const data = await getVendorStatement(db, req.params.id, companyId);
    if (!data) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `vendor-statement-${req.params.id}`, {
        content: [
          { text: `Statement — ${data.entity_name}`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', 'auto', 'auto', '*', 'auto', 'auto', 'auto'],
              body: [
                ['Date', 'Type', 'Reference', 'Description', 'Debit', 'Credit', 'Running Balance'].map((h) => ({ text: h, bold: true })),
                ...data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]),
                [{ text: '', colSpan: 5 }, {}, {}, {}, {}, { text: 'CLOSING BALANCE', bold: true }, { text: String(data.closing_balance), bold: true }],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)'];
      const dataRows: any[][] = data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]);
      dataRows.push(['', '', '', '', '', 'CLOSING BALANCE', data.closing_balance]);
      await sendXlsx(res, `vendor-statement-${req.params.id}`, 'Statement', headers, dataRows);
      return;
    }
    res.json(data);
  });
```

with:

```typescript
  vendors.get('/:id/statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const companyName = getActiveCompanyName(req);
    const data = await getVendorStatement(db, req.params.id, companyId);
    if (!data) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `vendor-statement-${req.params.id}`, {
        content: [
          { text: `Statement — ${data.entity_name}`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', 'auto', 'auto', '*', 'auto', 'auto', 'auto'],
              body: [
                ['Date', 'Type', 'Reference', 'Description', 'Debit', 'Credit', 'Running Balance'].map((h) => ({ text: h, bold: true })),
                ...data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]),
                [{ text: '', colSpan: 5 }, {}, {}, {}, {}, { text: 'CLOSING BALANCE', bold: true }, { text: String(data.closing_balance), bold: true }],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
      }, companyName);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)'];
      const dataRows: any[][] = data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]);
      dataRows.push(['', '', '', '', '', 'CLOSING BALANCE', data.closing_balance]);
      await sendXlsx(res, `vendor-statement-${req.params.id}`, 'Statement', headers, dataRows, companyName);
      return;
    }
    res.json(data);
  });
```

- [ ] **Step 4: Purchase invoice export**

Replace:

```typescript
  invoices.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('purchase_invoices').selectAll().where('company_id', '=', companyId ?? '').orderBy('date', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (inv) => {
        const vendor = await db.selectFrom('vendors').select('name').where('vendor_id', '=', inv.vendor_id).executeTakeFirst();
        return [inv.invoice_number, vendor?.name ?? '', inv.date, inv.due_date, inv.total_amount, inv.amount_paid, inv.status];
      }),
    );
    const headers = ['Invoice #', 'Vendor', 'Date', 'Due Date', 'Total (N)', 'Paid (N)', 'Status'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'purchase-invoices', 'Purchase Invoices', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'purchase-invoices', 'Purchase Invoices', headers, dataRows);
  });
```

with:

```typescript
  invoices.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('purchase_invoices').selectAll().where('company_id', '=', companyId ?? '').orderBy('date', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (inv) => {
        const vendor = await db.selectFrom('vendors').select('name').where('vendor_id', '=', inv.vendor_id).executeTakeFirst();
        return [inv.invoice_number, vendor?.name ?? '', inv.date, inv.due_date, inv.total_amount, inv.amount_paid, inv.status];
      }),
    );
    const headers = ['Invoice #', 'Vendor', 'Date', 'Due Date', 'Total (N)', 'Paid (N)', 'Status'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'purchase-invoices', 'Purchase Invoices', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'purchase-invoices', 'Purchase Invoices', headers, dataRows, companyName);
  });
```

- [ ] **Step 5: Purchase invoice print**

Replace:

```typescript
  invoices.get('/:id/print/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const data = await serializeInvoice(db, invoice);
    const outstanding = Math.max(0, invoice.total_amount - invoice.amount_paid);
    sendPdf(res, `purchase-invoice-${invoice.invoice_number}`, {
```

with:

```typescript
  invoices.get('/:id/print/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const data = await serializeInvoice(db, invoice);
    const outstanding = Math.max(0, invoice.total_amount - invoice.amount_paid);
    sendPdf(res, `purchase-invoice-${invoice.invoice_number}`, {
```

Then find the closing of that same `sendPdf` call — it ends with (from the file):

```typescript
        { text: `Total: ₦${invoice.total_amount.toLocaleString()}`, bold: true },
        { text: `Paid: ₦${invoice.amount_paid.toLocaleString()}` },
        { text: `Outstanding: ₦${outstanding.toLocaleString()}`, bold: true },
      ],
      styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
    });
  });
```

Replace only the final `});` of that specific call (the one closing the purchase-invoice-print `sendPdf`) with `}, companyName);`:

```typescript
        { text: `Total: ₦${invoice.total_amount.toLocaleString()}`, bold: true },
        { text: `Paid: ₦${invoice.amount_paid.toLocaleString()}` },
        { text: `Outstanding: ₦${outstanding.toLocaleString()}`, bold: true },
      ],
      styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
    }, companyName);
  });
```

- [ ] **Step 6: Item export**

Replace:

```typescript
  items.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('items').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const dataRows = await Promise.all(
      rows.map(async (i) => {
        const vendor = i.vendor_id ? await db.selectFrom('vendors').select('name').where('vendor_id', '=', i.vendor_id).executeTakeFirst() : null;
        return [i.name, i.item_type, vendor?.name ?? '', i.cost_price, i.selling_price];
      }),
    );
    const headers = ['Name', 'Type', 'Vendor', 'Cost Price (N)', 'Selling Price (N)'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'items', 'Items', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'items', 'Items', headers, dataRows);
  });
```

with:

```typescript
  items.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('items').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const dataRows = await Promise.all(
      rows.map(async (i) => {
        const vendor = i.vendor_id ? await db.selectFrom('vendors').select('name').where('vendor_id', '=', i.vendor_id).executeTakeFirst() : null;
        return [i.name, i.item_type, vendor?.name ?? '', i.cost_price, i.selling_price];
      }),
    );
    const headers = ['Name', 'Type', 'Vendor', 'Cost Price (N)', 'Selling Price (N)'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'items', 'Items', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'items', 'Items', headers, dataRows, companyName);
  });
```

- [ ] **Step 7: Typecheck**

Run: `cd desktop/page_desktop && npm run typecheck`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add desktop/page_desktop/src/server/routes/payables.ts
git commit -m "feat: show company name on desktop payables exports, statement, and invoice print"
```

---

## Task 17: Desktop — wire company name through receivables routes

**Files:**
- Modify: `desktop/page_desktop/src/server/routes/receivables.ts:7,75-86,88-124,203-219,231-263`

- [ ] **Step 1: Import `getActiveCompanyName`**

Replace:

```typescript
import { getActiveCompanyId } from '../lib/rbac';
```

with:

```typescript
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
```

- [ ] **Step 2: Customer export**

Replace:

```typescript
  customers.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('customers').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const headers = ['Name', 'Type', 'Email', 'Phone'];
    const dataRows = rows.map((c) => [c.name, c.customer_type, c.email, c.phone]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'customers', 'Customers', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'customers', 'Customers', headers, dataRows);
  });
```

with:

```typescript
  customers.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('customers').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const headers = ['Name', 'Type', 'Email', 'Phone'];
    const dataRows = rows.map((c) => [c.name, c.customer_type, c.email, c.phone]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'customers', 'Customers', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'customers', 'Customers', headers, dataRows, companyName);
  });
```

- [ ] **Step 3: Customer statement**

Replace:

```typescript
  customers.get('/:id/statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const data = await getCustomerStatement(db, req.params.id, companyId);
    if (!data) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `customer-statement-${req.params.id}`, {
        content: [
          { text: `Statement — ${data.entity_name}`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', 'auto', 'auto', '*', 'auto', 'auto', 'auto'],
              body: [
                ['Date', 'Type', 'Reference', 'Description', 'Debit', 'Credit', 'Running Balance'].map((h) => ({ text: h, bold: true })),
                ...data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]),
                [{ text: '', colSpan: 5 }, {}, {}, {}, {}, { text: 'CLOSING BALANCE', bold: true }, { text: String(data.closing_balance), bold: true }],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)'];
      const dataRows: any[][] = data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]);
      dataRows.push(['', '', '', '', '', 'CLOSING BALANCE', data.closing_balance]);
      await sendXlsx(res, `customer-statement-${req.params.id}`, 'Statement', headers, dataRows);
      return;
    }
    res.json(data);
  });
```

with:

```typescript
  customers.get('/:id/statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const companyName = getActiveCompanyName(req);
    const data = await getCustomerStatement(db, req.params.id, companyId);
    if (!data) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `customer-statement-${req.params.id}`, {
        content: [
          { text: `Statement — ${data.entity_name}`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', 'auto', 'auto', '*', 'auto', 'auto', 'auto'],
              body: [
                ['Date', 'Type', 'Reference', 'Description', 'Debit', 'Credit', 'Running Balance'].map((h) => ({ text: h, bold: true })),
                ...data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]),
                [{ text: '', colSpan: 5 }, {}, {}, {}, {}, { text: 'CLOSING BALANCE', bold: true }, { text: String(data.closing_balance), bold: true }],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
      }, companyName);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)'];
      const dataRows: any[][] = data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]);
      dataRows.push(['', '', '', '', '', 'CLOSING BALANCE', data.closing_balance]);
      await sendXlsx(res, `customer-statement-${req.params.id}`, 'Statement', headers, dataRows, companyName);
      return;
    }
    res.json(data);
  });
```

- [ ] **Step 4: Sales invoice export**

Replace:

```typescript
  invoices.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('sales_invoices').selectAll().where('company_id', '=', companyId ?? '').orderBy('date', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (inv) => {
        const customer = await db.selectFrom('customers').select('name').where('customer_id', '=', inv.customer_id).executeTakeFirst();
        return [inv.invoice_number, customer?.name ?? '', inv.date, inv.due_date, inv.total_amount, inv.amount_received, inv.status];
      }),
    );
    const headers = ['Invoice #', 'Customer', 'Date', 'Due Date', 'Total (N)', 'Received (N)', 'Status'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'sales-invoices', 'Sales Invoices', headers, dataRows);
      return;
    }
    await sendXlsx(res, 'sales-invoices', 'Sales Invoices', headers, dataRows);
  });
```

with:

```typescript
  invoices.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('sales_invoices').selectAll().where('company_id', '=', companyId ?? '').orderBy('date', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (inv) => {
        const customer = await db.selectFrom('customers').select('name').where('customer_id', '=', inv.customer_id).executeTakeFirst();
        return [inv.invoice_number, customer?.name ?? '', inv.date, inv.due_date, inv.total_amount, inv.amount_received, inv.status];
      }),
    );
    const headers = ['Invoice #', 'Customer', 'Date', 'Due Date', 'Total (N)', 'Received (N)', 'Status'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'sales-invoices', 'Sales Invoices', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'sales-invoices', 'Sales Invoices', headers, dataRows, companyName);
  });
```

- [ ] **Step 5: Sales invoice print**

Replace:

```typescript
  invoices.get('/:id/print/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const data = await serializeInvoice(db, invoice);
    const outstanding = Math.max(0, invoice.total_amount - invoice.amount_received);
    sendPdf(res, `sales-invoice-${invoice.invoice_number}`, {
```

with:

```typescript
  invoices.get('/:id/print/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const data = await serializeInvoice(db, invoice);
    const outstanding = Math.max(0, invoice.total_amount - invoice.amount_received);
    sendPdf(res, `sales-invoice-${invoice.invoice_number}`, {
```

Then, mirroring Task 16 Step 5, that same `sendPdf` call ends with:

```typescript
        { text: `Total: ₦${invoice.total_amount.toLocaleString()}`, bold: true },
        { text: `Received: ₦${invoice.amount_received.toLocaleString()}` },
        { text: `Outstanding: ₦${outstanding.toLocaleString()}`, bold: true },
      ],
      styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
    });
  });
```

Replace the closing `});` with `}, companyName);`:

```typescript
        { text: `Total: ₦${invoice.total_amount.toLocaleString()}`, bold: true },
        { text: `Received: ₦${invoice.amount_received.toLocaleString()}` },
        { text: `Outstanding: ₦${outstanding.toLocaleString()}`, bold: true },
      ],
      styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
    }, companyName);
  });
```

- [ ] **Step 6: Typecheck**

Run: `cd desktop/page_desktop && npm run typecheck`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add desktop/page_desktop/src/server/routes/receivables.ts
git commit -m "feat: show company name on desktop receivables exports, statement, and invoice print"
```

---

## Task 18: Desktop — wire company name through reports routes

**Files:**
- Modify: `desktop/page_desktop/src/server/routes/reports.ts:5,20-77,79-134,136-186,188-239`

- [ ] **Step 1: Import `getActiveCompanyName`**

Replace:

```typescript
import { getActiveCompanyId } from '../lib/rbac';
```

with:

```typescript
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
```

- [ ] **Step 2: Trial balance**

Replace:

```typescript
  router.get('/trial-balance/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

with:

```typescript
  router.get('/trial-balance/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

Then replace:

```typescript
    if (fmt === 'pdf') {
      sendPdf(res, `trial-balance-${dateFrom}-${dateTo}`, {
        content: [
          { text: `Trial Balance (${dateFrom} to ${dateTo})`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', '*', 'auto', 'auto', 'auto'],
              body: [
                ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'].map(bold),
                ...netted.map((r) => [r.code, r.name, r.account_type, r.display_debit || '', r.display_credit || '']),
                [{ text: '', colSpan: 3 }, {}, {}, bold(String(totalD)), bold(String(totalC))],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'];
      const dataRows: any[][] = netted.map((r) => [r.code, r.name, r.account_type, r.display_debit || null, r.display_credit || null]);
      dataRows.push(['', 'TOTALS', '', totalD, totalC]);
      await sendXlsx(res, `trial-balance-${dateFrom}-${dateTo}`, 'Trial Balance', headers, dataRows);
      return;
    }
```

with:

```typescript
    if (fmt === 'pdf') {
      sendPdf(res, `trial-balance-${dateFrom}-${dateTo}`, {
        content: [
          { text: `Trial Balance (${dateFrom} to ${dateTo})`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', '*', 'auto', 'auto', 'auto'],
              body: [
                ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'].map(bold),
                ...netted.map((r) => [r.code, r.name, r.account_type, r.display_debit || '', r.display_credit || '']),
                [{ text: '', colSpan: 3 }, {}, {}, bold(String(totalD)), bold(String(totalC))],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] } },
      }, companyName);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Code', 'Account', 'Type', 'Debit (N)', 'Credit (N)'];
      const dataRows: any[][] = netted.map((r) => [r.code, r.name, r.account_type, r.display_debit || null, r.display_credit || null]);
      dataRows.push(['', 'TOTALS', '', totalD, totalC]);
      await sendXlsx(res, `trial-balance-${dateFrom}-${dateTo}`, 'Trial Balance', headers, dataRows, companyName);
      return;
    }
```

- [ ] **Step 3: Income statement**

Replace:

```typescript
  router.get('/income-statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

with:

```typescript
  router.get('/income-statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

Then replace:

```typescript
    if (fmt === 'pdf') {
      sendPdf(res, `income-statement-${dateFrom}-${dateTo}`, {
        content: [
          { text: `Income Statement (${dateFrom} to ${dateTo})`, style: 'title' },
          { text: 'REVENUE', style: 'section' },
          ...data.revenue.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Total Revenue: ₦${data.total_revenue.toLocaleString()}`, bold: true },
          { text: 'COST OF SALES', style: 'section' },
          ...data.cost_of_sales.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Gross Profit: ₦${data.gross_profit.toLocaleString()}`, bold: true },
          { text: 'EXPENSES', style: 'section' },
          ...data.expenses.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Total Expenses: ₦${data.total_expenses.toLocaleString()}`, bold: true },
          { text: `Net Surplus / (Deficit): ₦${data.net_surplus.toLocaleString()}`, bold: true, margin: [0, 10, 0, 0] },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] }, section: { bold: true, margin: [0, 8, 0, 4] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Account', 'Type', 'Amount (N)'];
      const rows: any[][] = [
        ['REVENUE', '', ''],
        ...data.revenue.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Total Revenue', '', data.total_revenue],
        ['COST OF SALES', '', ''],
        ...data.cost_of_sales.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Gross Profit', '', data.gross_profit],
        ['EXPENSES', '', ''],
        ...data.expenses.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Total Expenses', '', data.total_expenses],
        ['Net Surplus / (Deficit)', '', data.net_surplus],
      ];
      await sendXlsx(res, `income-statement-${dateFrom}-${dateTo}`, 'Income Statement', headers, rows);
      return;
    }
```

with:

```typescript
    if (fmt === 'pdf') {
      sendPdf(res, `income-statement-${dateFrom}-${dateTo}`, {
        content: [
          { text: `Income Statement (${dateFrom} to ${dateTo})`, style: 'title' },
          { text: 'REVENUE', style: 'section' },
          ...data.revenue.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Total Revenue: ₦${data.total_revenue.toLocaleString()}`, bold: true },
          { text: 'COST OF SALES', style: 'section' },
          ...data.cost_of_sales.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Gross Profit: ₦${data.gross_profit.toLocaleString()}`, bold: true },
          { text: 'EXPENSES', style: 'section' },
          ...data.expenses.map((r: any) => ({ text: `${r.name}  —  ₦${r.balance.toLocaleString()}` })),
          { text: `Total Expenses: ₦${data.total_expenses.toLocaleString()}`, bold: true },
          { text: `Net Surplus / (Deficit): ₦${data.net_surplus.toLocaleString()}`, bold: true, margin: [0, 10, 0, 0] },
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] }, section: { bold: true, margin: [0, 8, 0, 4] } },
      }, companyName);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Account', 'Type', 'Amount (N)'];
      const rows: any[][] = [
        ['REVENUE', '', ''],
        ...data.revenue.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Total Revenue', '', data.total_revenue],
        ['COST OF SALES', '', ''],
        ...data.cost_of_sales.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Gross Profit', '', data.gross_profit],
        ['EXPENSES', '', ''],
        ...data.expenses.map((r: any) => [r.name, r.account_type, r.balance]),
        ['Total Expenses', '', data.total_expenses],
        ['Net Surplus / (Deficit)', '', data.net_surplus],
      ];
      await sendXlsx(res, `income-statement-${dateFrom}-${dateTo}`, 'Income Statement', headers, rows, companyName);
      return;
    }
```

- [ ] **Step 4: Balance sheet**

Replace:

```typescript
  router.get('/balance-sheet/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

with:

```typescript
  router.get('/balance-sheet/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

Then replace:

```typescript
      sendPdf(res, `balance-sheet-${asOfDate}`, {
        content: [
          { text: `Balance Sheet (as of ${asOfDate})`, style: 'title' },
          ...section('Assets', data.assets, data.total_assets),
          ...section('Liabilities', data.liabilities, data.total_liabilities),
          ...section('Equity', data.equity, data.total_equity),
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] }, section: { bold: true, margin: [0, 8, 0, 4] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Account', 'Type', 'Balance (N)'];
      const rows: any[][] = [];
      for (const [label, items, total] of [
        ['ASSETS', data.assets, data.total_assets],
        ['LIABILITIES', data.liabilities, data.total_liabilities],
        ['EQUITY', data.equity, data.total_equity],
      ] as const) {
        rows.push([label, '', '']);
        for (const r of items as any[]) rows.push([r.name, r.account_type, r.balance]);
        rows.push([`Total ${(label as string).charAt(0) + (label as string).slice(1).toLowerCase()}`, '', total]);
      }
      await sendXlsx(res, `balance-sheet-${asOfDate}`, 'Balance Sheet', headers, rows);
      return;
    }
```

with:

```typescript
      sendPdf(res, `balance-sheet-${asOfDate}`, {
        content: [
          { text: `Balance Sheet (as of ${asOfDate})`, style: 'title' },
          ...section('Assets', data.assets, data.total_assets),
          ...section('Liabilities', data.liabilities, data.total_liabilities),
          ...section('Equity', data.equity, data.total_equity),
        ],
        styles: { title: { fontSize: 14, bold: true, margin: [0, 0, 0, 10] }, section: { bold: true, margin: [0, 8, 0, 4] } },
      }, companyName);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Account', 'Type', 'Balance (N)'];
      const rows: any[][] = [];
      for (const [label, items, total] of [
        ['ASSETS', data.assets, data.total_assets],
        ['LIABILITIES', data.liabilities, data.total_liabilities],
        ['EQUITY', data.equity, data.total_equity],
      ] as const) {
        rows.push([label, '', '']);
        for (const r of items as any[]) rows.push([r.name, r.account_type, r.balance]);
        rows.push([`Total ${(label as string).charAt(0) + (label as string).slice(1).toLowerCase()}`, '', total]);
      }
      await sendXlsx(res, `balance-sheet-${asOfDate}`, 'Balance Sheet', headers, rows, companyName);
      return;
    }
```

- [ ] **Step 5: GL detail**

Replace:

```typescript
  router.get('/gl-detail/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

with:

```typescript
  router.get('/gl-detail/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company.' });
      return;
    }
```

Then replace:

```typescript
    if (fmt === 'pdf') {
      sendPdf(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, {
        content: [
          { text: `GL Detail — ${data.account_code} ${data.account_name} (${dateFrom} to ${dateTo})`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', 'auto', '*', 'auto', 'auto', 'auto', 'auto'],
              body: [
                ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'].map(bold),
                ...data.lines.map((l) => [l.date, l.reference, l.entry_description, l.entry_type || 'MANUAL', l.side, l.amount, l.running_balance]),
                [{ text: '', colSpan: 5 }, {}, {}, {}, {}, bold('CLOSING BALANCE'), bold(String(data.closing_balance))],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 13, bold: true, margin: [0, 0, 0, 10] } },
      });
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'];
      const rows: any[][] = data.lines.map((l) => [l.date, l.reference, l.entry_description, l.entry_type || 'MANUAL', l.side, l.amount, l.running_balance]);
      rows.push(['', '', '', '', 'CLOSING BALANCE', '', data.closing_balance]);
      await sendXlsx(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, `GL ${data.account_code}`, headers, rows);
      return;
    }
```

with:

```typescript
    if (fmt === 'pdf') {
      sendPdf(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, {
        content: [
          { text: `GL Detail — ${data.account_code} ${data.account_name} (${dateFrom} to ${dateTo})`, style: 'title' },
          {
            table: {
              headerRows: 1,
              widths: ['auto', 'auto', '*', 'auto', 'auto', 'auto', 'auto'],
              body: [
                ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'].map(bold),
                ...data.lines.map((l) => [l.date, l.reference, l.entry_description, l.entry_type || 'MANUAL', l.side, l.amount, l.running_balance]),
                [{ text: '', colSpan: 5 }, {}, {}, {}, {}, bold('CLOSING BALANCE'), bold(String(data.closing_balance))],
              ],
            },
          },
        ],
        styles: { title: { fontSize: 13, bold: true, margin: [0, 0, 0, 10] } },
      }, companyName);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Reference', 'Description', 'Type', 'Side', 'Amount (N)', 'Running Balance (N)'];
      const rows: any[][] = data.lines.map((l) => [l.date, l.reference, l.entry_description, l.entry_type || 'MANUAL', l.side, l.amount, l.running_balance]);
      rows.push(['', '', '', '', 'CLOSING BALANCE', '', data.closing_balance]);
      await sendXlsx(res, `gl-detail-${data.account_code}-${dateFrom}-${dateTo}`, `GL ${data.account_code}`, headers, rows, companyName);
      return;
    }
```

- [ ] **Step 6: Typecheck**

Run: `cd desktop/page_desktop && npm run typecheck`
Expected: PASS

- [ ] **Step 7: Full desktop build**

Run: `cd desktop/page_desktop && npm run build`
Expected: PASS — this is the final regression gate for the whole desktop half of the plan (typecheck + esbuild bundling).

- [ ] **Step 8: Commit**

```bash
git add desktop/page_desktop/src/server/routes/reports.ts
git commit -m "feat: show company name on desktop report exports"
```

---

## Task 19: Manual verification

**Files:** none (verification only)

- [ ] **Step 1: Backend — spot-check one PDF and one XLSX**

Run: `cd backend && source venv/bin/activate && python manage.py runserver 0.0.0.0:8002` (with Neo4j and a seeded company/user available, per the project's normal dev setup). Log in, then hit `GET /api/accounts/export/?format=pdf` and `GET /api/accounts/export/?format=xlsx` in a browser or via `curl -H "Authorization: Bearer <token>"`. Confirm the PDF shows the company name above "Chart of Accounts" with a rule beneath it, and the XLSX has the company name (bold, merged, row 1) and "Accounts" (bold, row 2) above the column headers (row 4).

- [ ] **Step 2: Desktop — spot-check one PDF and one XLSX**

Run: `cd desktop/page_desktop && npm run dev` to launch the Electron app against the local SQLite DB. Navigate to Accounts → Export, download both PDF and XLSX, and confirm the same letterhead/header shape as Step 1 (allowing for pdfmake's Helvetica-based styling instead of the backend's serif letterhead).

- [ ] **Step 3: Spot-check an invoice document on both platforms**

Print a sales invoice (backend: `GET /api/receivables/invoices/<id>/print/`; desktop: the equivalent Electron UI action) and confirm the company name now appears as a small caps line above "Sales Invoice", above the invoice's own `#1f4e79` themed header — distinct from the letterhead style used on list/report exports.

No commit for this task — it is a verification pass over Tasks 1–18.
