# Company Name on PDF/XLSX Exports Design

## Goal

Every PDF and XLSX export — from both the Django backend (serving the Angular web app) and the Electron desktop app — shows the name of the company whose books the export belongs to, so a document can never be mistaken for another company's records.

## Scope

Covers all existing PDF and XLSX export endpoints: list exports (accounts, journal entries, bank accounts, budgets, vendors, customers, purchase/sales invoices, items), statements (customer/vendor), individual invoice documents (sales/purchase invoice), and the four report exports (trial balance, income statement, balance sheet, GL detail). Applies identically to `backend/` (Django/WeasyPrint/openpyxl) and `desktop/page_desktop/` (Express/pdfmake/exceljs). No Angular changes — the frontend only downloads blobs the backend already generates. No changes to the `Company` model (name only, no address/logo).

## Data Source

`Company.name` is already embedded in the JWT on both platforms (`token['company_name']` in `backend/config/urls.py`'s `SageTokenObtainPairSerializer`; mirrored in `desktop/page_desktop/src/server/lib/jwt.ts`). No new database lookup is needed at export time. Two new accessors are added, mirroring the existing `company_id` accessors exactly:

- `get_active_company_name(request)` in `backend/config/auth.py`, reading `request.auth.get('company_name')`.
- `getActiveCompanyName(req)` in `desktop/page_desktop/src/server/lib/rbac.ts`, reading `req.auth?.company_name ?? null`.

## Backend Architecture

`config/export_utils.py`'s `pdf_response` and `xlsx_response` take `request` as their first argument and inject the company name automatically, so every call site changes only by adding `request` as the first argument:

- `pdf_response(request, template_name, context, filename)` — merges `company_name` into the template context before rendering.
- `xlsx_response(request, headers, rows, filename, sheet_title='Export')` — writes a merged, bold company-name row (14pt) followed by a bold report-title row (11pt, from `sheet_title`), a blank row, then the existing bolded header row and data rows (row offsets shift by 3).

`reports/views.py` currently reimplements `_pdf_response`/`_xlsx_response` locally instead of using `config/export_utils.py`. This duplication is removed — `reports/views.py` imports and uses the shared helpers, and its four inline `Workbook`-building blocks (trial balance, income statement, balance sheet, GL detail) get the same company-name/title header treatment via a small shared helper (`write_xlsx_header(ws, company_name, title, num_cols)`) used both by `xlsx_response` and by `reports/views.py`'s manual workbook construction.

### Template changes

13 "list/report" templates (`account_list.html`, `bank_account_list.html`, `budget_list.html`, `entry_list.html`, both `invoice_list.html` templates, `item_list.html`, `vendor_list.html`, `vendor_statement.html`, `customer_list.html`, `customer_statement.html`, `balance_sheet.html`, `gl_detail.html`, `income_statement.html`, `trial_balance.html`) currently duplicate the same CSS boilerplate (`h1` + `.subtitle`, `#1a1a2e` theme). These are converted to `{% extends %}` a new shared base template, `backend/config/templates/config/_pdf_base.html`, which defines the letterhead (company name) and exposes `{% block title %}` and `{% block subtitle %}` for the existing per-report title/subtitle, plus `{% block content %}` for the table markup. This removes the duplicated CSS as a side effect of adding the letterhead consistently.

The 2 invoice-style templates (`sales_invoice.html`, `purchase_invoice.html`) keep their own distinct markup/theme (`#1f4e79`) and get one added line for the company name above the existing "Sales Invoice"/"Purchase Invoice" title, styled to match their own header block rather than the shared base.

## Desktop Architecture

`desktop/page_desktop/src/server/exports/pdf.ts`'s `sendPdf`/`sendTablePdf` and `exports/xlsx.ts`'s `sendXlsx` take a `companyName: string | null` parameter:

- `sendPdf`/`sendTablePdf` prepend a `{ text: companyName, style: 'letterhead' }` block (bold, larger, navy) plus a thin rule to the pdfmake `content` array before the existing title/table.
- `sendXlsx` writes the same merged-row structure as the backend's `xlsx_response` (company name row, title row, blank row, then headers) via `ExcelJS` cell merging.

Every route in `desktop/page_desktop/src/server/routes/*.ts` (`accounts.ts`, `budget.ts`, `reports.ts`, `journals.ts`, `banks.ts`, `payables.ts`, `receivables.ts`) calls `getActiveCompanyName(req)` once per export action and threads it into the existing `sendPdf`/`sendTablePdf`/`sendXlsx` call.

## Visual Spec

- **PDF letterhead:** company name set in a serif fallback stack (`Georgia, "Times New Roman", serif`), navy (`#1a1a2e` for list/report templates, `#1f4e79` for invoice templates), ~16-18px, above a thin 1px rule, positioned above the existing report/document title. No Google Fonts CDN dependency — both the backend (should render reliably even if the CDN is unreachable) and the desktop app (offline-first) avoid a network font fetch at render time. This is a deliberate divergence from pixel-exact brand fidelity (DM Serif Display), accepted by the user.
- **pdfmake letterhead:** same visual intent using the already-registered Helvetica font at bold weight, larger size, navy color — brand consistency here comes from color/weight/spacing rather than an exact typeface match, since pdfmake requires fonts to be pre-registered as files.
- **XLSX header:** row 1 = company name, bold, 14pt, merged across all data columns. Row 2 = report/sheet title, bold, 11pt. Row 3 = blank. Row 4 = existing bolded column headers. Existing per-cell styling (e.g. numeric column bolding on totals rows) is unaffected other than the 3-row offset.

## Error Handling

If `company_name` is absent from the JWT (a pre-company token, per `get_active_company_id`'s existing "0 or >1 memberships" case), the letterhead renders blank rather than raising — export endpoints already return a `400` for "No active company" before reaching export code in every current call site, so this is a defensive fallback, not an expected path.

## Testing

- Update the two existing mocked-`pdf_response` tests (`backend/receivables/tests.py`, `backend/payables/tests.py`) for the new `request`-first signature.
- Add/extend a test asserting `xlsx_response` and `pdf_response` inject the company name from a request's JWT claims into, respectively, the workbook and template context.
- Spot-check rendered output: generate one PDF and one XLSX from each platform (backend and desktop) and visually confirm the letterhead appears correctly and existing content/totals are unaffected by the row/content offset.

## Constraints

- No new dependencies (WeasyPrint, openpyxl, pdfmake, ExcelJS are all already in use).
- No `Company` model changes (name-only letterhead; no address/logo).
- No Angular changes.
- Existing export API routes, filenames, and content types are unchanged.
- Do not modify existing user changes outside the files required by this feature.
