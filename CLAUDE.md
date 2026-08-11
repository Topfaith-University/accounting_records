# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Page** is a university accounting records application for Topfaith University. Full-stack monorepo:
- **Backend**: Django + Django REST Framework (port 8080)
- **Frontend**: Angular 17 standalone-component app (port 4200)
- **Database**: SQLite for everything — Django auth/admin, invite codes/companies, and all domain data (accounts, journals, banks, payables, receivables, budget)

## Running the Project

```bash
# All services (recommended)
docker-compose up --build

# Backend only
cd backend && source venv/bin/activate && python manage.py runserver 0.0.0.0:8080

# Frontend only
cd frontend/sage-frontend && npm install && npm start

# Tests
cd backend && python manage.py test
cd backend && python manage.py test <app>.tests.<TestClass>.<test_method>  # single test

# No linting is configured (no flake8, no eslint)

# After adding/changing any model
cd backend && python manage.py makemigrations && python manage.py migrate
```

**Docker container names**: `django_backend`, `angular_frontend`.

**Docker entrypoint** (`backend/entrypoint.sh`) runs automatically on container start: migrations → collect static → create superuser (via `DJANGO_SUPERUSER_*` env vars) → create default groups (`Admin`, `Manager`, `Accountant`) → assign superuser to Admin group.

## Architecture

### Single-database pattern
Everything — built-in apps (auth, admin, sessions), the `users` app (`Company`, `Membership`, `InviteCode`), and every domain model (accounts, journals, banks, payables, receivables, budget) — is a standard `django.db.models.Model` in the single SQLite database. Domain models were migrated off Neo4j/neomodel in 2026-08; see git history on the `backend` branch for the cutover. Every domain model has a `company = models.ForeignKey(users.Company)` for multi-tenancy scoping, and `created_by`/`approved_by`/`voided_by` fields are `ForeignKey(auth.User, null=True, on_delete=SET_NULL)`, not raw username strings.

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
| `users/` | `/api/users/` | `InviteCode` (SQLite — invite-code gated registration) |
| `config/` | — | Django settings, root URL conf, JWT auth views |

### API style
All views are `viewsets.ViewSet` with DRF `DefaultRouter`, **except** `reports/` and `config/urls.py` auth views which use plain function-based views. Every app has a `serializers.py` with full DRF serializers.

**FK id fields on serializers** (e.g. `vendor_id`, `expense_account_id`, `ap_account_id`) are `serializers.PrimaryKeyRelatedField(source='vendor', queryset=...)` — readable and writable in one field, no manual reattachment needed. `created_by`/`approved_by`/`voided_by` are exposed as plain username strings via `serializers.CharField(source='created_by.username', read_only=True, default=None)`, preserving the JSON shape the frontend expects even though the underlying field is a `ForeignKey(User)`.

### Auth & RBAC
JWT via `djangorestframework-simplejwt`. Custom `SageTokenObtainPairSerializer` (in `config/urls.py`) embeds `username` and `groups` in the token payload.

- JWT lifetimes: 8h access token, 7d refresh, auto-rotation enabled
- All endpoints require `IsAuthenticated`
- Post/void operations on invoices and journal entries additionally check `request.user.groups.filter(name__in=['Manager', 'Admin'])`
- Invite code generation/revocation (`/api/users/invite-codes/`) requires Admin or Manager group membership

Frontend reads roles from the decoded JWT in `AuthService`. JWT tokens stored in `localStorage` under keys `page_access` and `page_refresh`.

### Settings non-obvious details
- `TIME_ZONE = 'Africa/Lagos'` (Nigeria timezone; UTC offsets apply)
- `CORS_ALLOW_ALL_ORIGINS = True` — permissive, dev only

### URL structure
```
/api/auth/token/            → obtain JWT
/api/auth/token/refresh/    → refresh JWT
/api/auth/me/               → current user info
/api/auth/register/         → invite-code gated registration (AllowAny)
/api/accounts/              → AccountViewSet
/api/banks/accounts/        → BankAccountViewSet
/api/banks/transactions/    → BankTransactionViewSet
/api/banks/transactions/import/ → CSV bank statement import (POST)
/api/banks/transactions/export/ → CSV/XLSX export (GET ?format=csv|xlsx)
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
/api/budget/budgets/{id}/variance/ → real-time actual vs budgeted (per-line ORM aggregate)
/api/users/invite-codes/    → InviteCode list/generate (Manager/Admin)
/api/reports/trial-balance/
/api/reports/income-statement/
/api/reports/balance-sheet/
/api/reports/gl-detail/
/api/reports/dashboard/
```

All report endpoints accept `?format=pdf|xlsx` query param for export.

### Domain model conventions
- Primary keys are `models.CharField(max_length=32, primary_key=True, default=config.ids.new_id, editable=False)` — a plain 32-char hex string, not `UUIDField`. `UUIDField` raises `ValidationError` (→ unhandled 500) on a malformed lookup value like a garbage URL path param; `CharField` just finds no match (→ clean 404), matching neomodel's old `UniqueIdProperty` behavior. Use `config.ids.new_id` for any new domain model's PK.
- `created_at`/`updated_at` are `auto_now_add=True` (set once at creation, never auto-updated on later saves) — this matches the old neomodel `default_now=True` semantics, since no code path ever manually updates `updated_at` after creation.
- Race-safe sequence numbers (bank transaction refs, AP/AR settlement refs, PI/SI invoice numbers, journal entry references) all go through `journals.models.Counter.next(key)` — a `select_for_update()`-guarded counter row, not a scan-and-increment query.

### AccountType enum
Located in `backend/accounts/enums.py`. Valid values: `Sales`, `Cost of Sales`, `Expenses`, `Income Tax`, `Non-Current Assets`, `Current Assets`, `Current Liabilities`, `Non-Current Liabilities`, `Owner's Equity`, `Other Incomes`.

`normal_balance` is required (`DEBIT`/`CREDIT`). Debit-normal types: `Cost of Sales`, `Expenses`, `Income Tax`, `Non-Current Assets`, `Current Assets`. All others are credit-normal. Frontend auto-calculates `normal_balance` from `account_type` — never send it independently.

### JournalEntry model
- `entry_type` choices: `MANUAL`, `AP_PAYMENT`, `AR_RECEIPT`, `BANK_TRANSACTION`, `BANK_RECON`
- Each UI form row expands to **two** `JournalLine` nodes: one `DEBIT` (from account) + one `CREDIT` (to account) of equal amount. Balance is guaranteed by construction — no sum comparison needed.
- `JournalEntry.description` is derived server-side by joining non-empty line descriptions with `"; "`.

### AP/AR auto-journal entry patterns
All auto-entries are created with `status='POSTED'`, `created_by`/`approved_by` = current user, `approved_at` = utcnow().

- **AP Invoice post**: DEBIT each expense account (per line) + CREDIT AP control account
- **AP Payment**: DEBIT AP control account + CREDIT bank GL account
- **AR Invoice post**: DEBIT AR control account + CREDIT each revenue account (per line)
- **AR Receipt**: DEBIT bank GL account + CREDIT AR control account

### Bank reconciliation workflow
`BankReconciliation.toggle_line()` connects/disconnects a `JournalLine` via a `RECONCILES` relationship. `complete()` sums all reconciled journal lines and compares against `statement_balance` — requires match within ₦0.01. `get_bank_gl_lines()` uses raw Cypher to fetch all POSTED lines affecting a bank's GL account.

### CSV bank statement import
`POST /api/banks/transactions/import/` — expected columns: `Date`, `Description`, `Amount`. Amount sign determines type: positive = RECEIPT, negative = PAYMENT. Skips zero-amount rows. Supports three date formats: `dd/mm/yyyy`, `mm/dd/yyyy`, `yyyy-mm-dd`. Returns `{created, skipped, errors: []}`.

### InviteCode model (`users/models.py`, SQLite)
Single-use, 7-day TTL codes in `TFU-XXXX-XXXX-XXXX` format. Fields: `code`, `created_by`, `expires_at`, `used_by`, `used_at`. `status` property returns `active` / `used` / `expired`.

---

## Frontend

Angular 17 with standalone components. No NgModules — every component declares its own `imports` array. All routes use lazy loading: `.then(m => m.ComponentName)`. Services use **axios** (not Angular's HttpClient) with base URL `http://localhost:8080/api/`.

### Services (one per backend app)
All in `src/app/services/`.

| Service file | Backend app |
|---|---|
| `accounts.service.ts` | accounts |
| `banks.service.ts` | bank accounts |
| `bank-transactions.service.ts` | bank transactions + CSV import/export |
| `journals.service.ts` | journals |
| `payables.service.ts` | payables (vendors, invoices, items) |
| `receivables.service.ts` | receivables (customers, invoices) |
| `reports.service.ts` | reports |
| `budget.service.ts` | budget |
| `auth.service.ts` | JWT auth; decodes token to expose roles; exposes `register()` |
| `users.service.ts` | invite code CRUD (Admin/Manager only) |

### Shared components
Located in `src/app/shared/`.

**Smart select components** — each implements `ControlValueAccessor` (works with `formControlName` and `[(ngModel)]`):

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
- Container `<td>` must have `overflow:visible` (not `hidden`) or the dropdown will be clipped

**Pagination** (`PaginatePipe` + `PaginationComponent`):
- `PaginatePipe` — pure pipe: `items | paginate:page:pageSize`
- `PaginationComponent` — inputs `total`, `page`, `pageSize`; output `pageChange`; renders nothing when `total <= pageSize`
- All list components have `page = 1; pageSize = 25;` and reset `page = 1` when filters/tabs change

### Recurring frontend patterns

**Tab filtering** — used in entry-list, payables/receivables invoice-list:
```ts
activeTab: 'ALL' | 'DRAFT' | 'POSTED' | 'PAID' | 'VOID' = 'ALL';
setTab(tab) { this.activeTab = tab; this.page = 1; this.loadItems(); }
// service call passes status param when activeTab !== 'ALL'
```

**Inline form toggle** — used in account/vendor/customer/bank-account/item list components:
```ts
showForm = false;
editingXId: string | null = null;  // null = create mode
toggleForm() { ... }   // clears form
startEdit(item) { ... } // populates form, sets editingXId
cancelForm() { this.showForm = false; this.editingXId = null; }
```

**Status badge** — returns `[ngStyle]` object:
```ts
statusBadgeStyle(status: string) { /* gray/blue/green/red for DRAFT/POSTED/PAID/VOID */ }
```

**Data loading** — standard ngOnInit pattern:
```ts
async ngOnInit() {
  const [a, b] = await Promise.all([this.svcA.list(), this.svcB.list()]);
  this.items = a.results ?? a;  // unwraps DRF paginated or plain array
}
```

**RBAC getters** — on list components that have write actions:
```ts
get canManage() { return this.authService.isManagerOrAdmin(); }
get canDelete() { return this.authService.isAdmin(); }
```
Buttons are `*ngIf="canManage"` / `*ngIf="canDelete"`.

**Axios error handling**:
```ts
catch (e: any) {
  this.error = e.response?.data?.detail ?? JSON.stringify(e.response?.data);
}
```

### Item autofill pattern
`Item` nodes serve as **UI templates only** — selecting an item in an invoice line patches the reactive form group via `applyItem(index, itemId)`. Items are never stored as FK relationships on invoice lines. The item column only renders when `items.length > 0`.

### Route structure
```
/login                      → LoginComponent (public)
/signup                     → SignupComponent (public, invite-code gated)
/forgot-password            → ForgotPasswordComponent (public, informational only — no backend)
/dashboard                  → (auth-guarded shell)
/accounts                   → AccountListComponent
/journals                   → EntryListComponent
/journals/new               → EntryFormComponent
/journals/:id               → EntryDetailComponent
/banks                      → BankAccountListComponent
/banks/transactions         → BankTransactionListComponent
/banks/transactions/new     → BankTransactionFormComponent
/banks/reconciliations/:id  → BankReconciliationComponent
/payables/invoices          → InvoiceListComponent (AP)
/payables/vendors           → VendorListComponent
/payables/items             → ItemListComponent
/receivables/invoices       → SalesInvoiceListComponent
/receivables/customers      → CustomerListComponent
/budget                     → BudgetListComponent
/budget/new                 → BudgetFormComponent
/budget/:id                 → BudgetDetailComponent
/admin/invite-codes         → InviteCodesComponent (Manager/Admin only)
```

### Design system
CSS variables defined in global styles: `--navy-deep: #10002B`, `--navy-primary: #314991`, `--purple: #6F448D`, `--canvas: #F0F4FB`. Additional tokens: `--navy-light`, `--navy-subtle`, `--success`, `--danger`, `--border`, `--text-muted`, `--radius-xs/sm/md/lg`, `--shadow-xs`. Fonts: DM Serif Display (display/headings via `--font-serif`), Mulish (body via `--font-body`), JetBrains Mono (numbers via `--font-mono`).

### Environment / secrets
Backend reads from `backend/.env` via `python-decouple`. Required keys: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `NEO4J_BOLT_URL`. The `.env` file is committed — do not put production secrets there.
