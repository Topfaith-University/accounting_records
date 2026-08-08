# Chart of Accounts & Journal Entries Search

Date: 2026-08-08

## Problem

Neither the Chart of Accounts list nor the Journal Entries list can be searched. Users must scroll/paginate to find a specific account or entry.

## Chart of Accounts

Accounts are already fetched in full on page load and paginated client-side via `PaginatePipe` (no server pagination exists for `/api/accounts/`). Search is therefore a pure frontend change.

- `AccountListComponent` gets a `search = ''` field and a `filteredAccounts` getter that filters `this.accounts` by case-insensitive substring match against `code`, `name`, and `account_type`.
- The template iterates `filteredAccounts | paginate:page:pageSize` instead of `accounts`, and the `app-pagination` `total` input switches to `filteredAccounts.length`.
- Setting `search` resets `page` to `1`.
- No backend changes.

## Journal Entries

Entries are server-paginated (`page`, `page_size`, plus existing `status`/`date_from`/`date_to` filters in `JournalEntryViewSet.list`). Search needs a backend query param.

- Backend: `JournalEntryViewSet.list` accepts `?search=`. When present, filters:
  `Q(reference__icontains=search) | Q(description__icontains=search) | Q(lines__account__name__icontains=search)`,
  then `.distinct()` (the join through `lines__account` can duplicate rows when multiple lines on the same entry match).
- `JournalsService.getEntries()` params type gains `search?: string`.
- `EntryListComponent` gets `search = ''`, includes it in `loadEntries()` params when non-empty, and resets `page = 1` when it changes (same pattern as the existing date filters — reuses/extends the current apply-filter flow).
- Template: new search input next to the existing date-range filters.

## Out of scope

- No debounce on the journal search input (matches existing date-filter behavior, which also fires on every change).
- No search across other list pages (banks, payables, receivables) — not requested.
- No full-text/fuzzy search — `icontains` substring matching only, consistent with the rest of the app.

## Testing

- Backend: add a test to `journals/tests.py` covering `?search=` matching on reference, description, and account name (including the `.distinct()` dedup case).
- Frontend: manual verification in the browser (search Chart of Accounts by code/name/type; search Journal Entries by reference/description/account name, combined with existing status tab and date filters).
