# Chart of Accounts & Journal Entries Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Chart of Accounts list and the Journal Entries list searchable.

**Architecture:** Chart of Accounts is loaded in full client-side already, so search is a pure frontend filter. Journal Entries is server-paginated, so search is a new `?search=` query param on `JournalEntryViewSet.list` that matches reference, description, or the name of any account touched by the entry's lines.

**Tech Stack:** Django REST Framework (backend), Angular 17 standalone components (frontend).

## Global Constraints

- Search matching is case-insensitive substring (`icontains`), consistent with the rest of the app — no fuzzy/full-text search.
- No debounce on the journal search input — same behavior as the existing date-range filters, which also re-fetch on every change.
- Design spec: `docs/superpowers/specs/2026-08-08-coa-and-journal-search-design.md`

---

### Task 1: Backend — journal entry search filter

**Files:**
- Modify: `backend/journals/views.py` (`JournalEntryViewSet.list`, currently `backend/journals/views.py:20-38`)
- Test: `backend/journals/tests.py`

**Interfaces:**
- Consumes: `CompanyScopedTestCase` from `backend/payables/tests.py` (provides `self.company`, `self.client` authenticated as Admin, `get_active_company_id` patched).
- Produces: `GET /api/journals/entries/?search=<text>` — filters the existing paginated response, no shape change.

- [ ] **Step 1: Write the failing test**

Append to `backend/journals/tests.py`:

```python
from datetime import date

from payables.tests import CompanyScopedTestCase


class JournalEntrySearchTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from journals.models import JournalEntry, JournalLine

        self.rent_account = Account.objects.create(
            company=self.company, code='6100', name='Rent Expense',
            account_type='Expenses', normal_balance='DEBIT',
        )
        self.bank_account = Account.objects.create(
            company=self.company, code='1000', name='Main Bank',
            account_type='Current Assets', normal_balance='DEBIT',
        )

        self.rent_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-000001', date=date(2026, 7, 1),
            description='July office rent', status='POSTED',
            total_debit=500.0, total_credit=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.rent_entry, account=self.rent_account,
            side='DEBIT', amount=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.rent_entry, account=self.bank_account,
            side='CREDIT', amount=500.0,
        )

        self.other_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-000002', date=date(2026, 7, 2),
            description='Unrelated payment', status='POSTED',
            total_debit=100.0, total_credit=100.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.other_entry, account=self.bank_account,
            side='CREDIT', amount=100.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.other_entry, account=self.bank_account,
            side='DEBIT', amount=100.0,
        )

    def test_search_matches_reference(self):
        resp = self.client.get('/api/journals/entries/?search=JE-000002')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [e['entry_id'] for e in resp.data['results']]
        self.assertEqual(ids, [self.other_entry.entry_id])

    def test_search_matches_description(self):
        resp = self.client.get('/api/journals/entries/?search=office rent')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [e['entry_id'] for e in resp.data['results']]
        self.assertEqual(ids, [self.rent_entry.entry_id])

    def test_search_matches_account_name_without_duplicates(self):
        # rent_entry has two lines on bank_account-adjacent accounts; searching
        # by an account name that appears on multiple lines of the same entry
        # must still return that entry exactly once.
        resp = self.client.get('/api/journals/entries/?search=Main Bank')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [e['entry_id'] for e in resp.data['results']]
        self.assertEqual(sorted(ids), sorted([self.rent_entry.entry_id, self.other_entry.entry_id]))
        self.assertEqual(len(ids), len(set(ids)))

    def test_search_case_insensitive_and_no_match(self):
        resp = self.client.get('/api/journals/entries/?search=RENT')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data['results']), 1)

        resp = self.client.get('/api/journals/entries/?search=nonexistent-xyz')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['results'], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python manage.py test journals.tests.JournalEntrySearchTests -v 2`
Expected: FAIL — all four tests fail because `search` is currently ignored (every test returns both entries or errors on count mismatch).

- [ ] **Step 3: Implement the search filter**

In `backend/journals/views.py`, add the import and the filter inside `JournalEntryViewSet.list`, right after the existing `date_to` block (`backend/journals/views.py:33-36`) and before `qs = qs.order_by('-date')`:

```python
from django.db.models import Q
```

Add this at the top of the file alongside the existing `from datetime import datetime` import.

Then in `list`, insert after the `date_to` filter block and before `qs = qs.order_by('-date')`:

```python
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(description__icontains=search)
                | Q(lines__account__name__icontains=search)
            ).distinct()
```

The full `list` method should now read (unchanged lines omitted for brevity — only the new block is inserted between the date filters and the `order_by`):

```python
    def list(self, request):
        company_id = get_active_company_id(request)
        if not company_id:
            return Response({'detail': 'No active company.'}, status=status.HTTP_400_BAD_REQUEST)
        qs = JournalEntry.objects.filter(company_id=company_id)
        entry_status = request.query_params.get('status')
        if entry_status:
            qs = qs.filter(status=entry_status.upper())
        date_from = request.query_params.get('date_from')
        if date_from:
            try:
                qs = qs.filter(date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
            except ValueError:
                pass
        date_to = request.query_params.get('date_to')
        if date_to:
            try:
                qs = qs.filter(date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
            except ValueError:
                pass
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(description__icontains=search)
                | Q(lines__account__name__icontains=search)
            ).distinct()
        qs = qs.order_by('-date')
        page, page_size = parse_pagination_params(request)
        total, entries = paginate_queryset(qs, page, page_size)
        return Response(paginated_response(total, page, page_size, JournalEntrySerializer(entries, many=True).data))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python manage.py test journals.tests.JournalEntrySearchTests -v 2`
Expected: PASS — all four tests green.

- [ ] **Step 5: Run the full journals test suite to check for regressions**

Run: `cd backend && python manage.py test journals`
Expected: PASS — no existing tests broken.

- [ ] **Step 6: Commit**

```bash
git add backend/journals/views.py backend/journals/tests.py
git commit -m "feat: add search filter to journal entries list endpoint"
```

---

### Task 2: Frontend — Chart of Accounts search

**Files:**
- Modify: `frontend/sage-frontend/src/app/accounts/account-list/account-list.component.ts`
- Modify: `frontend/sage-frontend/src/app/accounts/account-list/account-list.component.html`

**Interfaces:**
- Consumes: existing `this.accounts: any[]` (populated in `loadAccounts()`, `frontend/sage-frontend/src/app/accounts/account-list/account-list.component.ts:53-70`), existing `PaginatePipe` and `app-pagination` component.
- Produces: `search: string` field and `filteredAccounts` getter on `AccountListComponent`, consumed by the template.

- [ ] **Step 1: Add `search` field and `filteredAccounts` getter**

In `frontend/sage-frontend/src/app/accounts/account-list/account-list.component.ts`, add a `search` field next to `pageSize` (after line 26):

```typescript
  page = 1;
  pageSize = 25;
  search = '';
```

Add a getter near the other getters (after `get canDelete()`, around line 41):

```typescript
  get filteredAccounts(): any[] {
    const term = this.search.trim().toLowerCase();
    if (!term) return this.accounts;
    return this.accounts.filter(a =>
      (a.code ?? '').toLowerCase().includes(term)
      || (a.name ?? '').toLowerCase().includes(term)
      || (a.account_type ?? '').toLowerCase().includes(term)
    );
  }
```

Add an `onSearchChange()` method next to `toggleForm()` (around line 72) so the page resets when the search text changes:

```typescript
  onSearchChange() {
    this.page = 1;
  }
```

- [ ] **Step 2: Wire the search input and switch the table to `filteredAccounts`**

In `frontend/sage-frontend/src/app/accounts/account-list/account-list.component.html`, add a search input inside the header row, right after the closing `</h3>` of the title block (after line 29, before the `@if (showForm)` block on line 33):

```html
    <div class="form-row" style="margin-top:0.75rem;">
      <div class="form-full">
        <input [(ngModel)]="search" (ngModelChange)="onSearchChange()"
          placeholder="Search by code, name, or type…"
          style="width:100%;max-width:320px;padding:0.6rem 0.85rem;border:1px solid var(--gray-light);border-radius:var(--radius-sm);box-sizing:border-box;font-family:var(--font-sans);" />
      </div>
    </div>
```

Then update the table body (line 111) to iterate `filteredAccounts` instead of `accounts`:

```html
          @for (account of filteredAccounts | paginate:page:pageSize; track account.account_id) {
```

And update the empty-state message condition is unaffected (it already just checks `@empty`), but update the pagination `total` input (line 157) to use `filteredAccounts.length`:

```html
      <app-pagination [total]="filteredAccounts.length" [page]="page" [pageSize]="pageSize" (pageChange)="page = $event"></app-pagination>
```

- [ ] **Step 3: Manually verify in the browser**

Start the frontend (`cd frontend/sage-frontend && npm start`) and backend (`cd backend && python manage.py runserver 0.0.0.0:8082`), navigate to `/accounts`, and confirm:
- Typing in the search box filters the table by code, name, and type (case-insensitive).
- Clearing the search box restores the full list.
- Pagination controls reflect the filtered count, and reset to page 1 when the search text changes.
- Editing/creating an account (existing flows) still works unaffected.

- [ ] **Step 4: Commit**

```bash
git add frontend/sage-frontend/src/app/accounts/account-list/account-list.component.ts frontend/sage-frontend/src/app/accounts/account-list/account-list.component.html
git commit -m "feat: add search to Chart of Accounts list"
```

---

### Task 3: Frontend — Journal Entries search

**Files:**
- Modify: `frontend/sage-frontend/src/app/services/journals.service.ts` (`getEntries`, `frontend/sage-frontend/src/app/services/journals.service.ts:9-11`)
- Modify: `frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.ts`
- Modify: `frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.html`

**Interfaces:**
- Consumes: Task 1's `GET /api/journals/entries/?search=` backend support.
- Produces: `search: string` field on `EntryListComponent`, included in `loadEntries()` requests.

- [ ] **Step 1: Add `search` to the service params type**

In `frontend/sage-frontend/src/app/services/journals.service.ts`, change line 9:

```typescript
  getEntries(params?: { status?: string; date_from?: string; date_to?: string; search?: string; page?: number; page_size?: number }) {
```

- [ ] **Step 2: Add `search` field to the component and include it in requests**

In `frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.ts`, add `search = '';` next to `dateTo` (after line 21):

```typescript
  dateFrom = '';
  dateTo = '';
  search = '';
```

Update the `params` type and assembly in `loadEntries()` (lines 33-37):

```typescript
      const params: { status?: string; date_from?: string; date_to?: string; search?: string; page: number; page_size: number } =
        { page: this.page, page_size: this.pageSize };
      if (this.activeTab !== 'ALL') params.status = this.activeTab;
      if (this.dateFrom) params.date_from = this.dateFrom;
      if (this.dateTo) params.date_to = this.dateTo;
      if (this.search.trim()) params.search = this.search.trim();
```

Rename `applyDateFilter` to `applyFilters` (it now covers search too) — update both the method definition (lines 51-54) and its two call sites (`clearDateFilter` at line 59, and the template at line 38, 43 — updated in Step 3):

```typescript
  async applyFilters() {
    this.page = 1;
    await this.loadEntries();
  }

  async clearDateFilter() {
    this.dateFrom = '';
    this.dateTo = '';
    await this.applyFilters();
  }
```

- [ ] **Step 3: Wire the search input in the template**

In `frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.html`, update the two existing `(ngModelChange)="applyDateFilter()"` calls (lines 38 and 43) to `(ngModelChange)="applyFilters()"`.

Add a search input into the filter row (after the closing `</div>` of the "To" date field, before the `@if (hasDateFilter)` block — i.e. after line 45):

```html
  <div style="display:flex;align-items:center;gap:.5rem">
    <input [(ngModel)]="search" (ngModelChange)="applyFilters()"
      placeholder="Search reference, description, or account…"
      style="padding:.35rem .5rem;border:1px solid #ccc;border-radius:4px;font-size:.875rem;min-width:240px" />
  </div>
```

- [ ] **Step 4: Manually verify in the browser**

With both servers running, navigate to `/journals`, and confirm:
- Typing a reference (e.g. an existing `JE-...` number) filters the list server-side.
- Typing description text or an account name filters the list.
- Search combines correctly with the status tabs and date range (e.g. search + `POSTED` tab together narrow results further).
- Clearing the search box restores the unfiltered (or tab/date-filtered) list.
- Export buttons and row navigation to entry detail still work unaffected.

- [ ] **Step 5: Commit**

```bash
git add frontend/sage-frontend/src/app/services/journals.service.ts frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.ts frontend/sage-frontend/src/app/journals/entry-list/entry-list.component.html
git commit -m "feat: add search to Journal Entries list"
```
