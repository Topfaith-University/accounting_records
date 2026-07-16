# Vendor & Customer Statement Design

## Goal

Give each vendor and customer a per-entity transaction ledger with a running balance, so staff can see at a glance what's owed to a vendor or owed by a customer — without that figure being polluted by other vendors/customers sharing the same AP/AR control account in the GL.

## Approach

Build each statement directly from domain relationships already on the graph, not from GL account lines:

- **Vendor statement**: `Vendor.invoices` (`FROM_VENDOR`), filtered to `status IN ('POSTED', 'PAID')`. Each qualifying invoice contributes one CREDIT line (`total_amount`) — an invoice increases what we owe the vendor. Each invoice's `payments` (`PAYS_INVOICE`) contributes one DEBIT line (`amount`) — a payment reduces what we owe. Lines are sorted by date. Running balance follows AP's credit-normal convention: `running_balance += credit - debit`, so it reads directly as "amount currently owed to this vendor."
- **Customer statement**: mirrors this via `Customer.invoices` (`BILLED_TO`), filtered the same way. Each invoice contributes a DEBIT line (`total_amount`); each invoice's `receipts` (`RECEIVES_PAYMENT_FOR`) contributes a CREDIT line (`amount`). Running balance follows AR's debit-normal convention: `running_balance += debit - credit`, reading as "amount this customer currently owes us."

DRAFT and VOID invoices are excluded entirely — they carry no accounting impact yet. Invoices with no payments/receipts still appear as a single CREDIT/DEBIT line.

## Backend

New service functions:
- `payables/services.py: get_vendor_statement(vendor_id, company_id) -> dict | None`
- `receivables/services.py: get_customer_statement(customer_id, company_id) -> dict | None`

Both return `None` if the entity isn't found, else:

```python
{
  'entity_id': str,
  'entity_name': str,
  'lines': [
    {
      'date': 'YYYY-MM-DD',
      'type': 'INVOICE' | 'PAYMENT' | 'RECEIPT',
      'reference': str,        # invoice_number, or payment/receipt reference
      'description': str,
      'debit': float,
      'credit': float,
      'running_balance': float,
    },
    ...
  ],
  'closing_balance': float,
}
```

New read-only actions on the existing `VendorViewSet` and `CustomerViewSet`, following the `?format=json|pdf|xlsx` convention already used by `reports/gl-detail`:

- `GET /api/payables/vendors/{id}/statement/?format=pdf|xlsx` (default `json`)
- `GET /api/receivables/customers/{id}/statement/?format=pdf|xlsx`

404 if the vendor/customer doesn't exist in the active company. No RBAC restriction beyond `IsAuthenticated` — this is a read-only view, same tier as invoice/vendor list.

PDF templates (`payables/templates/payables/vendor_statement.html`, `receivables/templates/receivables/customer_statement.html`) reuse the layout already established by `reports/templates/reports/gl_detail.html`: Date / Reference / Description / Debit / Credit / Running Balance columns, closing balance in a `<tfoot>` row. XLSX export mirrors the `gl_detail` xlsx branch in `reports/views.py` (openpyxl, bold header row, closing balance appended as a final row).

## Frontend

- `vendor-list` and `customer-list`: add a **"Statement"** button in the row actions column, next to Edit/Delete (name stays plain text). Routes to the detail page.
- New routes:
  - `/payables/vendors/:id` → `VendorStatementComponent` (`app/payables/vendor-statement/`)
  - `/receivables/customers/:id` → `CustomerStatementComponent` (`app/receivables/customer-statement/`)
- Each page: header showing entity name and closing balance (color-coded like other balance displays — e.g. `var(--danger)` if negative/unexpected sign), Export PDF/XLSX buttons using the existing blob-download pattern (`exportFile('pdf'|'xlsx')` → service method → `axios.get(..., {responseType: 'blob'})` → trigger download), and a table rendering `lines` with columns Date / Type / Reference / Description / Debit / Credit / Running Balance.
- New service methods:
  - `payables.service.ts`: `getVendorStatement(id)`, `exportVendorStatement(id, format)`
  - `receivables.service.ts`: `getCustomerStatement(id)`, `exportCustomerStatement(id, format)`
- Loading/error/empty states follow the standard pattern used elsewhere (`loading`, `error` fields; empty table shows "No transactions yet" row).

## Testing

Backend unit tests (`payables/tests.py`, `receivables/tests.py`) construct a vendor/customer with a POSTED invoice and a partial payment/receipt, then assert:
- Running balance decreases correctly after the payment/receipt line.
- A DRAFT or VOID invoice does not appear in `lines` and does not affect `closing_balance`.
- `closing_balance` matches the final line's `running_balance`, and equals `total_amount - amount_paid` (or `amount_received`) summed across all qualifying invoices.
- Statement for an unknown vendor/customer id returns 404.

## Constraints

- Do not read from `AFFECTS_ACCOUNT` / GL account lines for this feature — that's the exact blending problem being avoided (see the earlier bank `current_balance` fix, same rationale).
- Reuse existing `xlsx_response`/`pdf_response` helpers and the `?format=` convention; don't invent a new export mechanism.
- No changes to invoice/payment/receipt posting logic — this is a read-only aggregation over existing data.
