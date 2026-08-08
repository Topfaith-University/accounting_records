# Bank Accounts & Bank Transactions Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Bank Accounts list and the Bank Transactions list searchable.

**Architecture:** Bank Accounts are loaded in full client-side already, so search is a pure frontend filter (same shape as Chart of Accounts). Bank Transactions is server-paginated, so search is a new `?search=` query param on `BankTransactionViewSet` matching reference, description, vendor name, or customer name — built with a client-side debounce and a request-sequencing guard from the start (the prior Journal Entries search feature shipped without these and needed a follow-up fix after final review; this time they're part of the task).

**Tech Stack:** Django REST Framework (backend), Angular 17 standalone components (frontend).

## Global Constraints

- Search matching is case-insensitive substring (`icontains`), consistent with the rest of the app — no fuzzy/full-text search.
- Bank Transactions search input is debounced ~300ms; the bank-account dropdown and date filters stay immediate (undebounced) — only free-text search fires a request per keystroke.
- Design spec: `docs/superpowers/specs/2026-08-08-bank-search-design.md`

---

### Task 1: Backend — bank transaction search filter

**Files:**
- Modify: `backend/banks/views.py` (`BankTransactionViewSet._build_transactions_qs`, `list`, `export` — currently `backend/banks/views.py:207-263`)
- Test: `backend/banks/tests.py`

**Interfaces:**
- Consumes: `CompanyScopedTestCase` from `backend/payables/tests.py` (provides `self.company`, `self.client` authenticated as Admin, `get_active_company_id` patched); `create_bank_transaction` from `backend/banks/services.py` (accepts `company_id`, `transaction_type`, `txn_date`, `description`, `source_bank_id`, `destination_bank_id`, `splits`, `amount`, `created_by`, `vendor_id=None`, `customer_id=None`, `reference=None`).
- Produces: `GET /api/banks/transactions/?search=<text>` and `GET /api/banks/transactions/export/?search=<text>` — filters the existing responses, no shape change.

- [ ] **Step 1: Write the failing test**

Append to `backend/banks/tests.py`:

```python
from payables.tests import CompanyScopedTestCase


class BankTransactionSearchTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from banks.models import BankAccount
        from banks.services import create_bank_transaction
        from payables.models import Vendor
        from receivables.models import Customer

        self.gl = Account.objects.create(
            company=self.company, code='1000', name='Bank GL',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        self.expense = Account.objects.create(
            company=self.company, code='6100', name='Office Supplies',
            account_type='Expenses', normal_balance='DEBIT',
        )
        self.bank = BankAccount.objects.create(
            company=self.company, name='Main Bank', bank_name='GTBank',
            account_number='0123456789', opening_balance_date=date(2026, 1, 1),
            gl_account=self.gl,
        )
        self.vendor = Vendor.objects.create(company=self.company, name='Acme Supplies')
        self.customer = Customer.objects.create(company=self.company, name='Jane Student')

        self.vendor_txn = create_bank_transaction(
            company_id=str(self.company.id), transaction_type='PAYMENT',
            txn_date=date(2026, 7, 1), description='Office chairs',
            source_bank_id=str(self.bank.bank_account_id), destination_bank_id=None,
            splits=[{'account_id': str(self.expense.account_id), 'amount': 200.0, 'description': 'Chairs'}],
            amount=None, created_by=self.user, vendor_id=str(self.vendor.vendor_id),
            reference='BT-0001',
        )
        self.customer_txn = create_bank_transaction(
            company_id=str(self.company.id), transaction_type='RECEIPT',
            txn_date=date(2026, 7, 2), description='Tuition payment',
            source_bank_id=str(self.bank.bank_account_id), destination_bank_id=None,
            splits=[{'account_id': str(self.expense.account_id), 'amount': 500.0, 'description': 'Tuition'}],
            amount=None, created_by=self.user, customer_id=str(self.customer.customer_id),
            reference='BT-0002',
        )
        self.plain_txn = create_bank_transaction(
            company_id=str(self.company.id), transaction_type='PAYMENT',
            txn_date=date(2026, 7, 3), description='Unrelated expense',
            source_bank_id=str(self.bank.bank_account_id), destination_bank_id=None,
            splits=[{'account_id': str(self.expense.account_id), 'amount': 50.0, 'description': 'Misc'}],
            amount=None, created_by=self.user, reference='BT-0003',
        )

    def test_search_matches_reference(self):
        resp = self.client.get('/api/banks/transactions/?search=BT-0003')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.plain_txn.transaction_id])

    def test_search_matches_description(self):
        resp = self.client.get('/api/banks/transactions/?search=tuition')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.customer_txn.transaction_id])

    def test_search_matches_vendor_name(self):
        resp = self.client.get('/api/banks/transactions/?search=Acme')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.vendor_txn.transaction_id])

    def test_search_matches_customer_name(self):
        resp = self.client.get('/api/banks/transactions/?search=Jane')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.customer_txn.transaction_id])

    def test_search_no_duplicate_rows(self):
        # Neither filter path joins a one-to-many relation, but assert
        # explicitly that a transaction with both vendor and customer unset
        # (or set) never appears twice in a single search response.
        resp = self.client.get('/api/banks/transactions/?search=BT-000')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), sorted([
            self.vendor_txn.transaction_id, self.customer_txn.transaction_id, self.plain_txn.transaction_id,
        ]))

    def test_search_case_insensitive_and_no_match(self):
        resp = self.client.get('/api/banks/transactions/?search=ACME')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data['results']), 1)

        resp = self.client.get('/api/banks/transactions/?search=nonexistent-xyz')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['results'], [])
```

Note: `date` must be imported at module scope in `backend/banks/tests.py` — check the existing `from datetime import date` import near the top of the file (already present per the existing `GenerateReferenceTest`) and reuse it; do not add a duplicate import.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python manage.py test banks.tests.BankTransactionSearchTests -v 2` (or, if the local venv can't load the codebase, `docker exec django_backend python manage.py test banks.tests.BankTransactionSearchTests -v 2` — check which environment works, matching how Task 1 of the prior journals-search plan was verified).
Expected: FAIL — all six tests fail because `search` is currently ignored.

- [ ] **Step 3: Implement the search filter**

In `backend/banks/views.py`, `_build_transactions_qs` currently reads (per `backend/banks/views.py:207-221`):

```python
    def _build_transactions_qs(self, company_id, bank_account_id=None, date_from=None, date_to=None):
        qs = BankTransaction.objects.filter(company_id=company_id)
        if bank_account_id:
            qs = qs.filter(Q(source_bank_id=bank_account_id) | Q(destination_bank_id=bank_account_id))
        if date_from:
            try:
                qs = qs.filter(date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
            except ValueError:
                pass
        if date_to:
            try:
                qs = qs.filter(date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
            except ValueError:
                pass
        return qs.select_related('source_bank', 'destination_bank', 'vendor', 'customer').order_by('-created_at')
```

Change the signature and add the search filter:

```python
    def _build_transactions_qs(self, company_id, bank_account_id=None, date_from=None, date_to=None, search=None):
        qs = BankTransaction.objects.filter(company_id=company_id)
        if bank_account_id:
            qs = qs.filter(Q(source_bank_id=bank_account_id) | Q(destination_bank_id=bank_account_id))
        if date_from:
            try:
                qs = qs.filter(date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
            except ValueError:
                pass
        if date_to:
            try:
                qs = qs.filter(date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
            except ValueError:
                pass
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(description__icontains=search)
                | Q(vendor__name__icontains=search)
                | Q(customer__name__icontains=search)
            )
        return qs.select_related('source_bank', 'destination_bank', 'vendor', 'customer').order_by('-created_at')
```

In `list` (`backend/banks/views.py:223-229`), currently:

```python
    def list(self, request):
        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id') or None
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        page, page_size = parse_pagination_params(request)

        qs = self._build_transactions_qs(company_id, bank_account_id, date_from, date_to)
```

Change to:

```python
    def list(self, request):
        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id') or None
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        search = request.query_params.get('search') or None
        page, page_size = parse_pagination_params(request)

        qs = self._build_transactions_qs(company_id, bank_account_id, date_from, date_to, search)
```

In `export` (`backend/banks/views.py:231-238`), currently:

```python
        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id') or None
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        fmt = request.query_params.get('format', 'csv')

        txns = list(self._build_transactions_qs(company_id, bank_account_id, date_from, date_to))
```

Change to:

```python
        company_id = get_active_company_id(request)
        bank_account_id = request.query_params.get('bank_account_id') or None
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None
        search = request.query_params.get('search') or None
        fmt = request.query_params.get('format', 'csv')

        txns = list(self._build_transactions_qs(company_id, bank_account_id, date_from, date_to, search))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python manage.py test banks.tests.BankTransactionSearchTests -v 2` (or the `docker exec` form used in Step 2).
Expected: PASS — all six tests green.

- [ ] **Step 5: Run the full banks test suite to check for regressions**

Run: `cd backend && python manage.py test banks` (or `docker exec django_backend python manage.py test banks`).
Expected: PASS — no existing tests broken.

- [ ] **Step 6: Commit**

```bash
git add backend/banks/views.py backend/banks/tests.py
git commit -m "feat: add search filter to bank transactions list and export endpoints"
```

---

### Task 2: Frontend — Bank Accounts search

**Files:**
- Modify: `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.ts`
- Modify: `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.html`

**Interfaces:**
- Consumes: existing `this.accounts: any[]` (populated in `loadData()`, `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.ts:59-73`), existing `PaginatePipe` and `app-pagination` component.
- Produces: `search: string` field and `filteredAccounts` getter on `BankAccountListComponent`, consumed by the template.

- [ ] **Step 1: Add `search` field and `filteredAccounts` getter**

In `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.ts`, add a `search` field next to `pageSize` (after line 25):

```typescript
  page = 1;
  pageSize = 25;
  search = '';
```

Add a getter near `isEditMode` (after line 47):

```typescript
  get filteredAccounts(): any[] {
    const term = this.search.trim().toLowerCase();
    if (!term) return this.accounts;
    return this.accounts.filter(a =>
      (a.name ?? '').toLowerCase().includes(term)
      || (a.account_number ?? '').toLowerCase().includes(term)
      || (a.bank_name ?? '').toLowerCase().includes(term)
    );
  }
```

Add an `onSearchChange()` method next to `toggleForm()` (around line 75):

```typescript
  onSearchChange() {
    this.page = 1;
  }
```

- [ ] **Step 2: Wire the search input and switch the table to `filteredAccounts`**

In `frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.html`, add a search input inside the header row, right after the closing `</h3>` of the title block (after line 29, before the `@if (showForm)` block on line 33):

```html
    <div class="form-row" style="margin-top:0.75rem;">
      <div class="form-full">
        <input [(ngModel)]="search" (ngModelChange)="onSearchChange()"
          placeholder="Search by name, account number, or bank…"
          style="width:100%;max-width:320px;padding:0.6rem 0.85rem;border:1px solid var(--gray-light);border-radius:var(--radius-sm);box-sizing:border-box;font-family:var(--font-sans);" />
      </div>
    </div>
```

Update the table body (line 118) to iterate `filteredAccounts` instead of `accounts`:

```html
          @for (acct of filteredAccounts | paginate:page:pageSize; track acct.bank_account_id) {
```

Update the `@empty` block (currently lines 155-161) to distinguish a no-results search from a genuinely empty list:

```html
          @empty {
            <tr>
              <td colspan="5" style="padding:2rem;text-align:center;color:var(--charcoal-light);font-style:italic;">
                @if (search.trim()) {
                  No bank accounts match your search.
                } @else {
                  No bank accounts yet. Click "+ New" to add your first bank account.
                }
              </td>
            </tr>
          }
```

Update the pagination `total` input (line 164) to use `filteredAccounts.length`:

```html
      <app-pagination [total]="filteredAccounts.length" [page]="page" [pageSize]="pageSize" (pageChange)="page = $event"></app-pagination>
```

- [ ] **Step 3: Manually verify in the browser**

Start the frontend (`cd frontend/sage-frontend && npm start`) and backend, navigate to `/banks`, and confirm:
- Typing in the search box filters the table by name, account number, and bank name (case-insensitive).
- A search with no matches shows "No bank accounts match your search." — not the "+ New" prompt.
- Clearing the search box restores the full list, and the empty-list message reappears if there truly are zero bank accounts.
- Pagination reflects the filtered count and resets to page 1 when the search text changes.
- Editing/creating a bank account (existing flows) still works unaffected.

- [ ] **Step 4: Commit**

```bash
git add frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.ts frontend/sage-frontend/src/app/banks/bank-account-list/bank-account-list.component.html
git commit -m "feat: add search to Bank Accounts list"
```

---

### Task 3: Frontend — Bank Transactions search (with debounce and request-sequencing guard)

**Files:**
- Modify: `frontend/sage-frontend/src/app/services/bank-transactions.service.ts` (`getAll`, `frontend/sage-frontend/src/app/services/bank-transactions.service.ts:9-16`)
- Modify: `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.ts`
- Modify: `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.html`

**Interfaces:**
- Consumes: Task 1's `GET /api/banks/transactions/?search=` backend support.
- Produces: `search: string` field on `BankTransactionListComponent`, included in `loadTransactions()` requests (debounced); `requestSeq` sequencing guard protecting all `loadTransactions()` callers (pagination, bank/date filters, search).

- [ ] **Step 1: Add `search` to the service params type**

In `frontend/sage-frontend/src/app/services/bank-transactions.service.ts`, change:

```typescript
  getAll(params: { bankAccountId?: string; dateFrom?: string; dateTo?: string; page?: number; pageSize?: number } = {}) {
    const p: Record<string, string | number> = {};
    if (params.bankAccountId) p['bank_account_id'] = params.bankAccountId;
    if (params.dateFrom) p['date_from'] = params.dateFrom;
    if (params.dateTo) p['date_to'] = params.dateTo;
    if (params.page) p['page'] = params.page;
    if (params.pageSize) p['page_size'] = params.pageSize;
    return axios.get(this.baseUrl, { params: p }).then(r => r.data);
  }
```

to:

```typescript
  getAll(params: { bankAccountId?: string; dateFrom?: string; dateTo?: string; search?: string; page?: number; pageSize?: number } = {}) {
    const p: Record<string, string | number> = {};
    if (params.bankAccountId) p['bank_account_id'] = params.bankAccountId;
    if (params.dateFrom) p['date_from'] = params.dateFrom;
    if (params.dateTo) p['date_to'] = params.dateTo;
    if (params.search) p['search'] = params.search;
    if (params.page) p['page'] = params.page;
    if (params.pageSize) p['page_size'] = params.pageSize;
    return axios.get(this.baseUrl, { params: p }).then(r => r.data);
  }
```

- [ ] **Step 2: Add `search` field, debounce, and the request-sequencing guard to the component**

In `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.ts`, add fields next to `dateTo` (after line 24):

```typescript
  dateFrom = '';
  dateTo = '';
  search = '';
  private requestSeq = 0;
  private searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
```

Replace `loadTransactions()` (currently lines 66-84):

```typescript
  private async loadTransactions() {
    this.loading = true;
    this.error = '';
    const seq = ++this.requestSeq;
    try {
      const data = await this.txnService.getAll({
        bankAccountId: this.selectedBankId || undefined,
        dateFrom: this.dateFrom || undefined,
        dateTo: this.dateTo || undefined,
        search: this.search.trim() || undefined,
        page: this.page,
        pageSize: this.pageSize,
      });
      if (seq !== this.requestSeq) return;
      this.transactions = data.results ?? data;
      this.total = data.count ?? data.results?.length ?? data.length ?? 0;
    } catch {
      if (seq !== this.requestSeq) return;
      this.error = 'Failed to load transactions.';
    } finally {
      if (seq === this.requestSeq) this.loading = false;
    }
  }
```

Replace `clearFilter()` and `hasFilter` (currently lines 96-105):

```typescript
  clearFilter() {
    this.cancelSearchDebounce();
    this.selectedBankId = '';
    this.dateFrom = '';
    this.dateTo = '';
    this.search = '';
    this.applyFilter();
  }

  get hasFilter(): boolean {
    return !!(this.selectedBankId || this.dateFrom || this.dateTo || this.search);
  }
```

Add debounce methods next to `applyFilter()` (after line 89):

```typescript
  onSearchChange() {
    this.cancelSearchDebounce();
    this.searchDebounceTimer = setTimeout(() => {
      this.searchDebounceTimer = null;
      this.applyFilter();
    }, 300);
  }

  private cancelSearchDebounce() {
    if (this.searchDebounceTimer !== null) {
      clearTimeout(this.searchDebounceTimer);
      this.searchDebounceTimer = null;
    }
  }
```

- [ ] **Step 3: Wire the search input in the template**

In `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.html`, add a search input into the filter bar, after the closing `</div>` of the "To" date field's `<div>` (after line 144, before the `@if (hasFilter)` Clear button block):

```html
  <div style="display:flex;align-items:center;gap:.5rem">
    <input [(ngModel)]="search" (ngModelChange)="onSearchChange()"
      placeholder="Search reference, description, vendor, or customer…"
      style="min-width:240px;padding:.4rem .6rem;font-size:.875rem;border:1.5px solid var(--border);border-radius:var(--radius-sm)" />
  </div>
```

- [ ] **Step 4: Manually verify in the browser**

With both servers running, navigate to `/banks/transactions`, and confirm:
- Typing a reference, description text, a vendor name, or a customer name filters the list server-side, firing only after you pause typing (~300ms) — not on every keystroke.
- Typing quickly (e.g. "Acme" character by character) does not flash intermediate/stale result sets — the list settles on the final search term's results.
- Search combines correctly with the bank-account dropdown and date range (all three narrow results together), and those two still apply immediately without waiting for a debounce.
- Clicking "Clear" resets the bank/date/search filters together and the Clear button/"Filtered — N results" indicator only show when at least one filter is active.
- Export buttons still work and reflect the active filters.

- [ ] **Step 5: Commit**

```bash
git add frontend/sage-frontend/src/app/services/bank-transactions.service.ts frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.ts frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.html
git commit -m "feat: add debounced search to Bank Transactions list"
```
