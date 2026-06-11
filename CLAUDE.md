# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

"Sage" is a university accounting records application for Topfaith University. Full-stack monorepo:
- **Backend**: Django + Django REST Framework (port 8002)
- **Frontend**: Angular 17 standalone-component app (port 4200)
- **Database**: Neo4j 5 (bolt port 7687, browser port 7474) for all domain data; SQLite for Django auth/admin only

## Running the Project

```bash
# All services (recommended)
docker-compose up --build

# Backend only
cd backend && source venv/bin/activate && python manage.py runserver 0.0.0.0:8002

# Frontend only
cd frontend/sage-frontend && npm install && npm start

# Tests
cd backend && python manage.py test
cd frontend/sage-frontend && npm test

# After adding/changing Neo4j node models (run inside Docker if local venv is missing deps)
docker exec django_backend python manage.py install_labels
```

## Architecture

### Dual-database pattern
Django's ORM (SQLite) is used **only** for built-in apps (auth, admin, sessions). All domain models are `neomodel.StructuredNode` subclasses stored in Neo4j. Never use `django.db.models.Model` for domain entities.

### Backend apps

| App | URL prefix | Key models |
|-----|-----------|------------|
| `accounts/` | `/api/accounts/` | `Account` (with `AccountType` enum, `normal_balance`) |
| `banks/` | `/api/banks/` | `BankAccount`, `BankTransaction`, `BankReconciliation` |
| `journals/` | `/api/journals/` | `JournalEntry`, `JournalLine`, `FiscalYear`, `AccountingPeriod` |
| `payables/` | `/api/payables/` | `Vendor`, `PurchaseInvoice`, `PurchaseInvoiceLine`, `APPayment`, `Item` |
| `receivables/` | `/api/receivables/` | `Customer`, `SalesInvoice`, `SalesInvoiceLine`, `ARReceipt` |
| `reports/` | `/api/reports/` | Function-based views only (no models) |
| `budget/` | `/api/budget/` | `Budget`, `BudgetLine` |
| `config/` | — | Django settings, root URL conf, JWT auth views |

### API style
All views are `viewsets.ViewSet` with DRF `DefaultRouter`, **except** `reports/` which uses plain function-based views. Every app has a `serializers.py` with full DRF serializers.

**`_serialize_*` helper pattern**: Write-only FK fields on serializers (e.g. `vendor_id`, `expense_account_id`) must be manually re-attached in `_serialize_*(node)` helpers that call `Serializer(node).data` then add each FK id back from relationships. All ViewSet methods call these helpers before returning responses.

### Auth & RBAC
JWT via `djangorestframework-simplejwt`. Custom `SageTokenObtainPairSerializer` (in `config/urls.py`) embeds `username` and `groups` in the token payload.

- All endpoints require `IsAuthenticated`
- Post/void operations on invoices and journal entries additionally check `request.user.groups.filter(name__in=['Manager', 'Admin'])`

Frontend reads roles from the decoded JWT in `AuthService`.

### URL structure
```
/api/auth/token/            → obtain JWT
/api/auth/token/refresh/    → refresh JWT
/api/auth/me/               → current user info
/api/accounts/              → AccountViewSet
/api/banks/accounts/        → BankAccountViewSet
/api/banks/transactions/    → BankTransactionViewSet
/api/banks/reconciliations/ → BankReconciliationViewSet
/api/journals/entries/      → JournalEntryViewSet
/api/journals/fiscal-years/ → FiscalYearViewSet
/api/journals/periods/      → AccountingPeriodViewSet
/api/payables/vendors/      → VendorViewSet
/api/payables/invoices/     → PurchaseInvoiceViewSet
/api/payables/items/        → ItemViewSet
/api/receivables/customers/ → CustomerViewSet
/api/receivables/invoices/  → SalesInvoiceViewSet
/api/budget/budgets/        → BudgetViewSet
/api/reports/trial-balance/
/api/reports/income-statement/
/api/reports/balance-sheet/
/api/reports/gl-detail/
/api/reports/dashboard/
```

### Neomodel conventions
- `UniqueIdProperty` for all primary keys
- Run `install_labels` after any model schema change
- `updated_at` uses `default_now=True` but is **not** auto-updated on save — set manually

### AccountType enum
Located in `backend/accounts/enums.py`. Valid values: `Sales`, `Cost of Sales`, `Expenses`, `Income Tax`, `Non-Current Assets`, `Current Assets`, `Current Liabilities`, `Non-Current Liabilities`, `Owner's Equity`, `Other Incomes`.

`normal_balance` is required (`DEBIT`/`CREDIT`). Debit-normal types: `Cost of Sales`, `Expenses`, `Income Tax`, `Non-Current Assets`, `Current Assets`. All others are credit-normal.

### JournalEntry entry_type choices
`MANUAL`, `AP_PAYMENT`, `AR_RECEIPT`, `BANK_TRANSACTION`

---

## Frontend

Angular 17 with standalone components. No NgModules — every component declares its own `imports` array.

### Services (one per backend app)
All in `src/app/services/`. Each uses **axios** (not Angular's HttpClient). Base URL is `http://localhost:8002`.

| Service file | Backend app |
|---|---|
| `accounts.service.ts` | accounts |
| `banks.service.ts` | bank accounts |
| `bank-transactions.service.ts` | bank transactions |
| `journals.service.ts` | journals |
| `payables.service.ts` | payables (vendors, invoices, items) |
| `receivables.service.ts` | receivables (customers, invoices) |
| `reports.service.ts` | reports |
| `budget.service.ts` | budget |
| `auth.service.ts` | JWT auth; decodes token to expose roles |

### Shared smart select components
Located in `src/app/shared/`. Each implements `ControlValueAccessor` so it works with both `formControlName` (reactive forms) and `[(ngModel)]` (template-driven).

| Component | `@Input()` | `@Output()` |
|---|---|---|
| `AccountSelectComponent` | `allAccounts: any[]` | `accountsChanged` |
| `BankSelectComponent` | `allBanks: any[]` | `banksChanged` |
| `VendorSelectComponent` | `allVendors: any[]` | `vendorsChanged` |
| `CustomerSelectComponent` | `allCustomers: any[]` | `customersChanged` |

All four follow the same pattern:
- Searchable typeahead dropdown with inline quick-create modal
- `+ Create…` button at the **top** of the dropdown list (with `border-bottom` separator, not `border-top`)
- `@HostListener('document:click')` closes dropdown on outside click
- List item click uses `(mousedown)` not `(click)` to fire before `blur`
- Parent passes `allX` array and listens to `xChanged` to refresh after quick-create

### Item autofill pattern
`Item` nodes serve as **UI templates only** — selecting an item in an invoice line patches the reactive form group via `applyItem(index, itemId)`. Items are never stored as FK relationships on invoice lines. The item column only renders when `items.length > 0`.

### Environment / secrets
Backend reads from `backend/.env` via `python-decouple`. Required keys: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `NEO4J_BOLT_URL`. The `.env` file is committed — do not put production secrets there.
