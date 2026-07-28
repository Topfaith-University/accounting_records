# Bank Transactions — Design Spec
_Date: 2026-05-26_

## Overview

Allow users to record financial transactions directly against a bank account without navigating the full journal entry form. The feature supports money in (receipts), money out (payments), and bank-to-bank transfers, with optional splits across multiple contra accounts. Every transaction posts immediately and auto-generates a balanced journal entry behind the scenes.

---

## Data Model

### New node: `BankTransaction` (in `backend/banks/models.py`)

| Field | Type | Notes |
|---|---|---|
| `transaction_id` | UniqueIdProperty | Primary key |
| `reference` | StringProperty | Auto-generated `BT-YYYY-NNNN`, unique index |
| `transaction_type` | StringProperty | `RECEIPT` / `PAYMENT` / `TRANSFER` |
| `date` | DateProperty | Required |
| `amount` | FloatProperty | Sum of splits (or transfer amount) |
| `description` | StringProperty | Required |
| `created_by` | StringProperty | Username of creator |
| `created_at` | DateTimeProperty | default_now=True |

**Relationships:**

| Relationship | Target | Cardinality | Notes |
|---|---|---|---|
| `FROM_BANK` | `BankAccount` | One | Source bank (always required) |
| `TO_BANK` | `BankAccount` | ZeroOrOne | Destination bank (TRANSFER only) |
| `GENERATES_ENTRY` | `JournalEntry` | One | The auto-created posted journal entry |

---

## Double-Entry Logic

### RECEIPT (money into source bank)
- Source bank GL account → **DEBIT**
- Each contra account in splits → **CREDIT**
- Total debits = Total credits = sum of split amounts

### PAYMENT (money out of source bank)
- Source bank GL account → **CREDIT**
- Each contra account in splits → **DEBIT**
- Total debits = Total credits = sum of split amounts

### TRANSFER (bank to bank)
- Source bank GL account → **CREDIT**
- Destination bank GL account → **DEBIT**
- `splits` array is empty; amount is specified directly
- Both bank accounts must have a linked GL account (`MAPS_TO_ACCOUNT`)

---

## Backend API

### Endpoints

All under `/api/banks/transactions/` via `BankTransactionViewSet`.

| Method | URL | Description | Auth |
|---|---|---|---|
| GET | `/api/banks/transactions/` | List transactions; filter by `?bank_account_id=` | Authenticated |
| POST | `/api/banks/transactions/` | Create and immediately post | Authenticated |
| GET | `/api/banks/transactions/{id}/` | Retrieve with full journal lines | Authenticated |

No update or delete endpoints. A posted transaction can only be reversed by voiding the linked journal entry through the existing journals workflow.

### POST request body

```json
{
  "transaction_type": "PAYMENT",
  "date": "2025-10-01",
  "description": "Utility bills payment",
  "source_bank_id": "<uuid>",
  "destination_bank_id": null,
  "splits": [
    { "account_id": "<uuid>", "amount": 45000.00, "description": "Electricity" },
    { "account_id": "<uuid>", "amount": 12000.00, "description": "Water" }
  ]
}
```

For TRANSFER: `splits` is empty, `destination_bank_id` is required, and `amount` is a top-level field instead.

### Files to create/modify

- `backend/banks/models.py` — Add `BankTransaction` node
- `backend/banks/serializers.py` — Add `BankTransactionSerializer`, `BankTransactionSplitSerializer`
- `backend/banks/services.py` — Add `generate_bank_transaction_reference()` and `create_bank_transaction()`
- `backend/banks/views.py` — Add `BankTransactionViewSet`
- `backend/banks/urls.py` — Register `transactions` router prefix
- `backend/journals/models.py` — Add `'BANK_TRANSACTION'` to `JournalEntry.entry_type` choices

### Auto-reference generation

`generate_bank_transaction_reference()` counts existing `BankTransaction` nodes for the current calendar year and returns `BT-{YYYY}-{N:04d}` (e.g., `BT-2026-0001`). Implemented as a Cypher count query for accuracy.

### Service: `create_bank_transaction()`

Single function, executed atomically:

1. Validate source bank exists and has a linked GL account
2. For TRANSFER: validate destination bank exists and has a linked GL account
3. Validate splits (≥1 split for RECEIPT/PAYMENT; each split amount > 0)
4. Generate reference via `generate_bank_transaction_reference()`
5. Build journal lines based on transaction type (see double-entry logic above)
6. Create `JournalEntry` with `entry_type='BANK_TRANSACTION'`, `status='POSTED'`, `created_by=username`
7. Create and connect all `JournalLine` nodes
8. Create `BankTransaction` node, connect `FROM_BANK`, `TO_BANK` (if transfer), `GENERATES_ENTRY`
9. Return `BankTransaction`

---

## Frontend

### New service

`src/app/services/bank-transactions.service.ts` — axios-based, methods:
- `getAll(bankAccountId?: string)` → list
- `getOne(id: string)` → detail with lines
- `create(data: object)` → create

### New components

#### 1. `BankTransactionListComponent`
- Path: `src/app/banks/bank-transaction-list/`
- Route: `/banks/transactions`
- Shows all transactions in a table: reference, date, bank account name, type badge, amount, description
- Bank account filter dropdown at top
- "+ New Transaction" button → `/banks/transactions/new`

#### 2. `BankTransactionFormComponent`
- Path: `src/app/banks/bank-transaction-form/`
- Route: `/banks/transactions/new`
- Accepts optional `?bank_id=` query param to pre-select the source bank
- Fields:
  - Transaction type: Receipt / Payment / Transfer (radio or segmented control)
  - Source bank account dropdown (all active bank accounts)
  - Destination bank account dropdown (TRANSFER only)
  - Date (defaults to today)
  - Description
  - Amount field (TRANSFER only)
  - Splits table (RECEIPT/PAYMENT): account selector, amount, optional memo; running total shown; "+ Add split" button
- Submit posts immediately; on success navigates to `/banks/{source_bank_id}`
- No draft state — form either submits successfully or shows an error

### Modified components

#### `BankAccountDetailComponent`
- Add a "Transactions" tab alongside existing tabs (Ledger, Reconciliations)
- Tab shows `BankTransactionListComponent` data filtered to this bank account
- Add "+ New Transaction" button linking to `/banks/transactions/new?bank_id={id}`

### Routing

Add to `app.routes.ts` inside shell children, before `/banks/:id`:

```
/banks/transactions/new  → BankTransactionFormComponent
/banks/transactions      → BankTransactionListComponent
```

### Navigation

Add "Transactions" child link under General Ledger → Bank Accounts in `shell.component.html`, pointing to `/banks/transactions`.

---

## Constraints & Error Cases

- Source bank must have a linked GL account (`MAPS_TO_ACCOUNT`) — return 400 if missing
- Destination bank (TRANSFER) must also have a linked GL account — return 400 if missing
- Splits must sum to > 0
- Each split amount must be > 0
- TRANSFER requires `destination_bank_id` ≠ `source_bank_id`
- RECEIPT/PAYMENT requires at least one split
- Reference collisions are prevented by the count-based generator (sequential within year)

---

## Out of Scope

- Editing or deleting bank transactions (use journal entry void)
- Recurring/scheduled transactions
- Attaching receipts or documents
- Multi-currency conversion
