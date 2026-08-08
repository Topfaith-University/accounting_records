# Bank Accounts & Bank Transactions Search

Date: 2026-08-08

## Problem

Neither the Bank Accounts list nor the Bank Transactions list can be searched. This is a follow-up to the Chart of Accounts / Journal Entries search work ([2026-08-08-coa-and-journal-search-design.md](2026-08-08-coa-and-journal-search-design.md)) and reuses its patterns, including two lessons from that feature's final review: build the search-input debounce and request-sequencing guard in from the start (don't ship the race condition and fix it later), and make sure "no results" messaging distinguishes "no records" from "no search matches".

## Bank Accounts

`BankAccountViewSet.list` returns the full, unpaginated list (no server pagination exists for `/api/banks/accounts/`), and `BankAccountListComponent` already paginates it client-side via `PaginatePipe`. Search is a pure frontend change, identical in shape to the Chart of Accounts change.

- `BankAccountListComponent` gets a `search = ''` field and a `filteredAccounts` getter that filters `this.accounts` by case-insensitive substring match against `name`, `account_number`, and `bank_name`.
- The template iterates `filteredAccounts | paginate:page:pageSize` instead of `accounts`, and the `app-pagination` `total` input switches to `filteredAccounts.length`.
- Setting `search` resets `page` to `1`.
- The `@empty` block distinguishes the two empty cases: when `search` is set and `filteredAccounts` is empty, show "No bank accounts match your search."; otherwise keep the existing "No bank accounts yet..." message. (This corrects a rough edge left in the Chart of Accounts version, where a no-match search shows a misleading "click + New" prompt — not fixed there since it was ruled non-blocking, but worth doing right here since we're building it fresh.)
- No backend changes.

## Bank Transactions

`BankTransactionViewSet.list` is server-paginated (`page`, `page_size`, plus existing `bank_account_id`/`date_from`/`date_to` filters built in `_build_transactions_qs`). Search needs a backend query param.

- Backend: `_build_transactions_qs` (used by both `list` and `export`) accepts an optional `search` argument. When present, filters:
  `Q(reference__icontains=search) | Q(description__icontains=search) | Q(vendor__name__icontains=search) | Q(customer__name__icontains=search)`.
  No `.distinct()` needed — each `BankTransaction` has at most one `vendor` and one `customer` FK (not a one-to-many line join like journal entries), so this filter cannot fan a single row into duplicates.
  `list` reads `request.query_params.get('search')` and passes it through; `export` does the same so exported data matches what's currently searched (matches existing behavior where `bank_account_id`/date filters are already honored by both `list` and `export`).
- `BankTransactionsService.getAll()` params gain `search?: string`, mapped to `search` in the request params (same pattern as `bankAccountId` → `bank_account_id`).
- `BankTransactionListComponent`:
  - Gets a `search = ''` field.
  - `loadTransactions()` includes `search: this.search.trim() || undefined` in the request params alongside the existing filters.
  - `clearFilter()` currently resets `selectedBankId`, `dateFrom`, `dateTo` then calls `applyFilter()` — extend it to also reset `search`.
  - `hasFilter` currently checks `selectedBankId || dateFrom || dateTo` — extend it to also check `search`. (No renaming needed here, unlike the journal entries case — these getters/methods are already named generically.)
  - New: a request-sequencing guard in `loadTransactions()` (a `requestSeq` counter, incremented per call, captured at call start, checked before applying the response on both the success and error paths) so a slow, stale response can never overwrite a newer one's results — built in from the start this time rather than discovered in review.
  - New: the search `<input>`'s `(ngModelChange)` goes through a ~300ms debounce (plain `setTimeout`/`clearTimeout`, matching the journals component's style — no new RxJS dependency) before calling `applyFilter()`. The bank-account dropdown and date inputs keep firing `applyFilter()` immediately, undebounced — only the free-text search field is debounced, since only free text produces a request per keystroke.

## Out of scope

- No debounce/sequencing changes to the bank-account or date filters — they already fire once per user action, not per keystroke.
- No search across bank reconciliations — not requested.
- No full-text/fuzzy search — `icontains` substring matching only, consistent with the rest of the app.
- No change to the CSV/XLSX export column set — `search` narrows which rows are exported, it doesn't add a column.

## Testing

- Backend: add tests to `banks/tests.py` covering `?search=` matching on reference, description, vendor name, and customer name, plus a case confirming a transaction with both a vendor and a customer set isn't duplicated (even though no join-fanout is expected, assert it explicitly since it's the same risk shape as the journals dedup test).
- Frontend: manual verification in the browser — search Bank Accounts by name/account number/bank name; search Bank Transactions by reference/description/vendor/customer name, combined with the existing bank-account and date filters; verify rapid typing doesn't show stale results (the debounce should collapse keystrokes, and the sequencing guard should protect against any residual race).
