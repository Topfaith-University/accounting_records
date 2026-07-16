# PRD — "Page Desktop" — Standalone Windows Accounting App (Python + Flet + SQLite)

> **Superseded 2026-07-15 by [`../electron-desktop-port/PRD.md`](../electron-desktop-port/PRD.md).** The Flet approach required hand-rebuilding every screen from this spec in an unfamiliar UI framework, which proved hard to build correctly. The Electron approach reuses the existing Angular frontend directly instead. This document is kept for reference — its data model (§3) and business logic spec (§4) were carried forward largely unchanged; do not use its UI/tech-stack sections (§2, §6, §7) for new work.

**Status:** Approved for build
**Source of truth for behavior:** the live Page web system (Django + Neo4j backend, Angular 17 frontend) in this repository, as of 2026-07-15. This PRD is a byte-for-byte behavioral port of that system into a new, independent, offline desktop stack — it does not talk to the existing backend at any point.

---

## 1. Overview & Goals

**What this is:** a single-file-installable Windows desktop application, built with Python and [Flet](https://flet.dev), that reproduces every screen, workflow, calculation, and business rule of the existing Page accounting system, but runs fully offline against a local SQLite database instead of a networked Django + Neo4j backend.

**Why it exists:**
- **Primary use, real accounting work**: lets Topfaith University run the same double-entry accounting workflows (chart of accounts, journal entries, bank reconciliation, AP/AR, budgets, financial reports) on a machine with no network access.
- **Secondary use, teaching/testing sandbox**: the same binary is handed to accounting students on lab/exam PCs so they can practice the full workflow hands-on. There is **no special exam mode** — students use the identical app an accountant would use. Any proctoring, data collection, or grading process happens outside the app (out of scope, see §11).

**Relationship to the existing system:** independent artifact. It is not a client of the Django API, does not require Neo4j, and does not sync with the web app's database. It is a from-scratch reimplementation of the same product requirements.

**Guiding constraint — total feature parity:** every endpoint, screen, computed value, validation rule, and even the *known quirks* of the current system (§10) must be reproduced. This PRD exists specifically so nothing gets silently dropped or "improved" during the port.

---

## 2. Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| UI framework | **Flet** (Python bindings over Flutter) | Single Python codebase produces a native Windows desktop app; supports the view/route model needed for ~30 screens; good enough theming control (colors, fonts, radii) to approximate the existing design system. |
| Local storage | **SQLite**, accessed via **SQLAlchemy ORM** (`sqlalchemy` + its bundled `sqlite3` driver) | One embedded file per install, zero server process. SQLAlchemy gives us declarative models with relationships/constraints/cascades close to the ergonomics the team is used to from Django, and its `Session` gives us transactional integrity for multi-row writes (e.g. posting a journal entry with N lines) — important since SQLite has no separate app-server enforcing this. Raw `sqlite3` was considered but rejected: the business logic layer (§4) does enough multi-table writes and idempotency checks that hand-written SQL would be harder to keep correct across ~20 tables. |
| Schema management | SQLAlchemy models define schema; `Base.metadata.create_all()` runs on first launch to create the DB file if absent. No migration framework needed for v1 (fresh installs only; if the schema changes between versions, ship a fresh DB and let the user re-seed, since there is no fleet-wide upgrade-in-place requirement). |
| Password hashing | Python stdlib `hashlib.pbkdf2_hmac` (no compiled dependency, packaging-safe) | Avoids adding a compiled wheel dependency (e.g. bcrypt) that could complicate single-.exe packaging on some Windows setups. Salted PBKDF2-SHA256, 100,000+ iterations, is adequate for a local single-user-at-a-time desktop app protecting local exam/accounting data. |
| XLSX export | **openpyxl** | Same library the existing backend already uses — exact same output shape achievable. |
| PDF export | **reportlab** (preferred) or **fpdf2** as fallback | Pure-Python, no native binary dependencies (rules out WeasyPrint, which needs GTK/Pango and would break single-.exe packaging). Either is acceptable; pick one and use it consistently for all PDF exports/prints. |
| Packaging | `flet build windows` (preferred) or PyInstaller as fallback, producing **one Windows `.exe` installer** | No separate Python install needed on lab machines. Fonts (§7) and the empty starter SQLite schema must be bundled as app resources, not downloaded. |
| Currency | Nigerian Naira, symbol `₦`, always 2 decimals, thousands separator: `f"₦{value:,.2f}"` | Matches the Angular `number:'1.2-2'` pipe behavior exactly. |
| Date/time | Local system clock only — no timezone conversion logic. The original backend pins `TIME_ZONE='Africa/Lagos'`; a single-machine offline desktop app has no cross-timezone concern, so all dates/timestamps are stored and displayed as the local machine's wall-clock time. This is a deliberate, documented simplification, not a missed requirement. | |

---

## 3. Data Model

All primary keys are `TEXT` UUID strings (mirrors `UniqueIdProperty` from neomodel) unless noted. All tables live in one SQLite file, e.g. `page_desktop.db`. Every table below is a direct translation of a neomodel `StructuredNode`; every relationship translation is noted.

### 3.1 Auth / RBAC tables (new relational equivalent of Django auth + `InviteCode`)

**`users`**
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | uuid |
| `username` | TEXT UNIQUE NOT NULL | |
| `password_hash` | TEXT NOT NULL | PBKDF2 salted hash |
| `email` | TEXT NULL | |
| `is_active` | INTEGER DEFAULT 1 | |
| `date_joined` | TEXT (ISO datetime) | |

**`groups`** — seeded on first run with exactly `Admin`, `Manager`, `Accountant` (mirrors `entrypoint.sh`'s default groups) plus `Staff` (created ad hoc the first time it's needed, exactly like the original Django `get_or_create('Staff')` — do not pre-seed it, replicate the lazy-creation behavior).
| Column | Type |
|---|---|
| `id` | TEXT PK |
| `name` | TEXT UNIQUE NOT NULL |

**`user_groups`** (join table, replaces Django's M2M): `user_id` FK→users, `group_id` FK→groups, PK(`user_id`,`group_id`).

**`invite_codes`**
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `code` | TEXT UNIQUE NOT NULL | format `TFU-XXXX-XXXX-XXXX`, generated from a cryptographically random token (`secrets.token_urlsafe`), each 4-char segment upper-cased |
| `created_by_id` | TEXT NULL FK→users | nullable (mirrors `on_delete=SET_NULL`) |
| `created_at` | TEXT | auto |
| `expires_at` | TEXT NOT NULL | `created_at + 7 days` default TTL |
| `used_by_id` | TEXT NULL FK→users | |
| `used_at` | TEXT NULL | |

Derived `status` (not stored, computed same as original `status` property): `'used'` if `used_by_id` set; else `'expired'` if now ≥ `expires_at`; else `'active'`.

### 3.2 Accounts

**`accounts`**
| Column | Type | Notes |
|---|---|---|
| `account_id` | TEXT PK | |
| `code` | TEXT UNIQUE NOT NULL | auto-generated if blank (§4.1); **immutable after creation** |
| `name` | TEXT NOT NULL | |
| `account_type` | TEXT NOT NULL | one of the 10 `AccountType` values (§4.10) |
| `normal_balance` | TEXT NOT NULL CHECK(`DEBIT`,`CREDIT`) | |
| `description` | TEXT DEFAULT '' | |
| `opening_balance` | REAL DEFAULT 0.0 | **immutable after creation** |
| `is_active` | INTEGER DEFAULT 1 | soft-delete flag |
| `is_system` | INTEGER DEFAULT 0 | system accounts (e.g. Opening Balance Equity) cannot be deleted |
| `parent_id` | TEXT NULL FK→accounts.account_id | self-referential tree, one parent max (mirrors `CHILD_OF` ZeroOrOne) |
| `created_at`, `updated_at` | TEXT | `updated_at` is **not** auto-touched on update — set manually only where the original does (nowhere, currently — replicate: never auto-update it) |

### 3.3 Journals

**`fiscal_years`**: `year_id` PK, `name` NOT NULL, `start_date`, `end_date` (dates, NOT NULL), `status` CHECK(`OPEN`,`CLOSED`) DEFAULT `OPEN`, `created_at`.

**`accounting_periods`**: `period_id` PK, `name` NOT NULL, `start_date`, `end_date` NOT NULL, `period_number` INTEGER NOT NULL, `status` CHECK(`OPEN`,`CLOSED`) DEFAULT `OPEN`, `fiscal_year_id` FK→fiscal_years NOT NULL.

**`journal_entries`**
| Column | Type | Notes |
|---|---|---|
| `entry_id` | TEXT PK | |
| `reference` | TEXT UNIQUE NOT NULL | auto-generated `JN-YYYYMMDD-XXXX` if blank (§4.2) |
| `date` | TEXT (date) NOT NULL | |
| `description` | TEXT NOT NULL | server-derived: join of non-empty line descriptions with `"; "`, default `"Journal Entry"` |
| `status` | TEXT CHECK(`DRAFT`,`POSTED`,`VOID`) DEFAULT `DRAFT` | |
| `entry_type` | TEXT CHECK(`MANUAL`,`BANK_RECON`,`AP_PAYMENT`,`AR_RECEIPT`,`BANK_TRANSACTION`) DEFAULT `MANUAL` | |
| `total_debit`, `total_credit` | REAL DEFAULT 0.0 | |
| `created_by` | TEXT NOT NULL | username |
| `approved_by` | TEXT DEFAULT '' | |
| `approved_at` | TEXT NULL | |
| `voided_by` | TEXT DEFAULT '' | |
| `voided_at` | TEXT NULL | |
| `period_id` | TEXT NULL FK→accounting_periods | present for schema parity but **intentionally never populated** anywhere in the app, exactly as in the original (dead field — see §10) |
| `created_at`, `updated_at` | TEXT | |

**`journal_lines`**: `line_id` PK, `entry_id` FK→journal_entries NOT NULL (cascade delete with entry), `account_id` FK→accounts NOT NULL, `side` CHECK(`DEBIT`,`CREDIT`) NOT NULL, `amount` REAL NOT NULL (must be > 0), `description` TEXT DEFAULT '', `created_at`.

### 3.4 Banks

**`bank_accounts`**: `bank_account_id` PK, `name` NOT NULL, `account_number` TEXT UNIQUE NULL, `bank_name` NOT NULL, `currency` DEFAULT `'NGN'`, `opening_balance` REAL DEFAULT 0.0 (**immutable after creation**), `opening_balance_date` NOT NULL, `is_active` DEFAULT 1, `gl_account_id` FK→accounts NULL, `created_at`, `updated_at`.

**`bank_reconciliations`**: `reconciliation_id` PK, `bank_account_id` FK→bank_accounts NOT NULL, `period_start`, `period_end` NOT NULL, `statement_balance` REAL NOT NULL, `status` CHECK(`DRAFT`,`COMPLETED`) DEFAULT `DRAFT`, `created_by` NOT NULL, `completed_at` NULL, `created_at`.

**`reconciliation_lines`** (relational replacement for the `RECONCILES` many-to-many relationship, toggled on/off): `reconciliation_id` FK→bank_reconciliations, `journal_line_id` FK→journal_lines, PK(`reconciliation_id`,`journal_line_id`). Presence of a row = "reconciled".

**`bank_transactions`**: `transaction_id` PK, `reference` TEXT UNIQUE NOT NULL, `transaction_type` CHECK(`RECEIPT`,`PAYMENT`,`TRANSFER`) NOT NULL, `date` NOT NULL, `amount` REAL NOT NULL, `description` DEFAULT '', `created_by` NOT NULL, `source_bank_id` FK→bank_accounts NOT NULL, `destination_bank_id` FK→bank_accounts NULL (TRANSFER only), `journal_entry_id` FK→journal_entries NOT NULL, `vendor_id` FK→vendors NULL, `customer_id` FK→customers NULL, `created_at`, `updated_at`.

**`bank_txn_counters`** (atomic reference counter, replaces the Cypher `MERGE` counter node): `year` INTEGER PK, `seq` INTEGER NOT NULL.

**`invoice_settlement_counters`** (atomic counter for AP/AR settlement references): `prefix` TEXT, `invoice_number` TEXT, `seq` INTEGER NOT NULL, PK(`prefix`,`invoice_number`).

### 3.5 Payables

**`vendors`**: `vendor_id` PK, `name` NOT NULL (only truly required field), `email` DEFAULT '', `phone` DEFAULT '', `address` DEFAULT '', `is_active` DEFAULT 1, `created_at`.

**`purchase_invoices`**: `invoice_id` PK, `invoice_number` TEXT UNIQUE NOT NULL (auto `PI-YYYY-XXXX`), `date`, `due_date` NOT NULL, `description` DEFAULT '', `status` CHECK(`DRAFT`,`POSTED`,`PAID`,`VOID`) DEFAULT `DRAFT` — **note: there is deliberately no `PARTIAL` status**, see §10 — `total_amount` DEFAULT 0.0, `amount_paid` DEFAULT 0.0, `created_by` NOT NULL, `vendor_id` FK→vendors NOT NULL, `ap_account_id` FK→accounts NOT NULL, `journal_entry_id` FK→journal_entries NULL, `created_at`.

**`purchase_invoice_lines`**: `line_id` PK, `invoice_id` FK→purchase_invoices NOT NULL (cascade delete), `description` DEFAULT '', `quantity` REAL DEFAULT 1.0, `unit_price` REAL DEFAULT 0.0, `amount` NOT NULL, `expense_account_id` FK→accounts NOT NULL.

**`items`**: `item_id` PK, `name` NOT NULL, `description` DEFAULT '', `unit_price` DEFAULT 0.0, `item_type` CHECK(`PRODUCT`,`SERVICE`) DEFAULT `SERVICE`, `is_active` DEFAULT 1, `vendor_id` FK→vendors NULL, `expense_account_id` FK→accounts NULL, `revenue_account_id` FK→accounts NULL, `created_at`. Items are **templates only** — no invoice line ever stores a reference back to an item.

**`ap_payments`**: `payment_id` PK, `invoice_id` FK→purchase_invoices NOT NULL, `payment_date` NOT NULL, `amount` NOT NULL, `reference` DEFAULT '', `created_by` NOT NULL, `bank_account_id` FK→bank_accounts NOT NULL, `journal_entry_id` FK→journal_entries NULL, `created_at`.

### 3.6 Receivables (mirror of Payables)

**`customers`**: `customer_id` PK, `name` NOT NULL, `email`/`phone`/`address` DEFAULT '', `customer_type` CHECK(`STUDENT`,`EXTERNAL`) DEFAULT `EXTERNAL`, `is_active` DEFAULT 1, `created_at`.

**`sales_invoices`**: mirrors `purchase_invoices` with `customer_id` FK→customers, `ar_account_id` FK→accounts, `amount_received` instead of `amount_paid`. Invoice number auto `SI-YYYY-XXXX`.

**`sales_invoice_lines`**: mirrors purchase lines with `revenue_account_id` FK→accounts.

**`ar_receipts`**: mirrors `ap_payments` with `receipt_date` instead of `payment_date`.

### 3.7 Budget

**`budgets`**: `budget_id` PK, `name` NOT NULL, `fiscal_year` TEXT NOT NULL (free text, e.g. `"2025/2026"` — **not** an FK to `fiscal_years`, exactly as today), `status` CHECK(`DRAFT`,`APPROVED`) DEFAULT `DRAFT`, `created_by` NOT NULL, `approved_by` DEFAULT '', `approved_at` NULL, `created_at`.

**`budget_lines`**: `line_id` PK, `budget_id` FK→budgets NOT NULL (cascade delete), `account_id` FK→accounts NOT NULL, `budgeted_amount` NOT NULL. Constraint: within one budget, an account may appear on **at most one** line (enforce at the application layer during create, exactly like the original serializer's `validate()`).

---

## 4. Business Logic Spec

Every rule below must be reproduced with the exact same thresholds, rounding, and ordering of checks as the original.

### 4.1 Account code auto-generation
If `code` is left blank on create, generate it: map `account_type` to a 4-digit prefix —
```
Sales -> '4000', Cost of Sales -> '5000', Expenses -> '6000', Income Tax -> '6000',
Non-Current Assets -> '1000', Current Assets -> '1100', Current Liabilities -> '2000',
Non-Current Liabilities -> '2100', Owner's Equity -> '3000', Other Incomes -> '4000',
(any other/default) -> '9000'
```
Find the maximum existing numeric suffix among accounts whose `code` starts with that prefix, increment by 1, and produce `f"{prefix}{next_seq:04d}"` (i.e. the prefix is not re-truncated — the result is the 4-digit prefix directly followed by a 4-digit zero-padded sequence, e.g. second account under prefix `1000` becomes `"10000001"`). This scan-then-insert is **not** wrapped in an atomic counter — replicate the same race-condition-prone behavior as the original (single-user desktop app makes the race window irrelevant in practice, but do not "fix" it into an atomic counter).
If `code` is supplied, it must be unique — reject with a validation error otherwise.
`code` and `opening_balance` are **write-once**: any update request must silently drop changes to these two fields rather than erroring.

### 4.2 Journal entry reference auto-generation
If `reference` is blank on create: format `JN-YYYYMMDD-XXXX` using **today's date** (not the entry's `date` field), scanning existing references with that day's prefix for the max existing 4-digit suffix, incrementing, zero-padding to 4 digits. Not atomic — replicate as-is (§10).
If supplied, `reference` must be globally unique across all journal entries.

### 4.3 Manual journal entry validation & balance rule
A journal entry must have **at least 2 lines**. Sum all `DEBIT` line amounts and all `CREDIT` line amounts; `round(total_debit, 2)` must equal `round(total_credit, 2)`, else reject with an error naming both totals. This check runs **twice** in the original: once at creation/update time, and again independently inside the posting step (§4.4) — replicate both checks (defense in depth, not redundant to remove).

The entry-creation UI always builds entries as pairs: each "row" the user fills in produces exactly **two** `journal_lines`: one `DEBIT` against the "from" account and one `CREDIT` against the "to" account, both for the same amount. `journal_entries.description` is computed server-side (not user-entered directly) as the non-empty per-line descriptions joined with `"; "`, defaulting to `"Journal Entry"` if every line description is blank.

### 4.4 Posting and voiding a journal entry
**Post** (`entry.status` must currently be `DRAFT`):
1. Must have ≥ 2 lines.
2. Re-check debit == credit balance (rounded 2dp) — reject if unbalanced.
3. Every line's account must exist and have `is_active = 1` — reject otherwise.
4. Set `status='POSTED'`, `approved_by=<acting username>`, `approved_at=<now>`.

**Void** (`entry.status` must currently be `POSTED` — DRAFT and already-VOID entries cannot be voided): set `status='VOID'`, `voided_by`, `voided_at=<now>`. **Voiding never rewrites or reverses the underlying line amounts.** VOID entries are simply excluded from every balance/report query going forward (§4.5 filters on `status='POSTED'` only).

Neither posting nor voiding a journal entry requires any particular role in the original system — any authenticated user may post or void any DRAFT/POSTED entry (see the RBAC matrix in §5.3; this is one of the "replicate as-is" quirks in §10).

### 4.5 Account balance computation
The canonical, single source of truth for any account's balance — **never** a stored running total:
```
total_debits  = SUM(journal_lines.amount) WHERE side='DEBIT'  AND journal_entries.status='POSTED' [AND date <= as_of_date]
total_credits = SUM(journal_lines.amount) WHERE side='CREDIT' AND journal_entries.status='POSTED' [AND date <= as_of_date]
balance = round(total_debits - total_credits, 2)   if account.normal_balance == 'DEBIT'
balance = round(total_credits - total_debits, 2)   otherwise
```
Returns `0.0` if the account has no matching lines (or doesn't exist). `as_of_date` is optional — omit the date filter entirely when not given.

### 4.6 Opening balance auto-posting (idempotent)
When an `Account` (or a `BankAccount` linked to a GL account) is created with a non-zero `opening_balance`, automatically post a journal entry seeding it:
- Deterministic reference: `f"OB-{account_id}"` (keyed to the **GL account's** id, not the bank account's).
- **Idempotency guard**: if a journal entry with that exact reference already exists, do nothing and return — never post a duplicate, even if called again (e.g. because a `BankAccount` is re-linked to the same GL account, or a save is retried).
- Otherwise create a 2-line `POSTED` entry, `entry_type='MANUAL'`, dated today: normal-balance side of `abs(opening_balance)` on the target account, opposite side on a system "Opening Balance Equity" account (get-or-create it: `code='3900'`, `name='Opening Balance Equity'`, `account_type="Owner's Equity"`, `normal_balance='CREDIT'`, `is_system=True`). If `opening_balance < 0`, swap the two sides.
- Re-linking a `BankAccount` to a *different* GL account on update re-triggers this idempotent poster for the new account (since the reference key changes), which is expected and correct — it is not a bug to fix.

### 4.7 Bank transaction creation (manual entry, CSV import, and AP/AR auto-generated all funnel through this)
Inputs: `transaction_type` (`RECEIPT`/`PAYMENT`/`TRANSFER`), date, description, `source_bank_id`, optional `destination_bank_id`, `splits` (list of `{account_id, amount, description}`), `created_by`, optional `vendor_id`/`customer_id`, optional explicit `reference`.

1. Validate `transaction_type` is one of the three allowed values.
2. Resolve `source_bank`; it must exist and have a linked `gl_account_id` (reject with an actionable message telling the user to link a GL account first, otherwise).
3. **TRANSFER**: `destination_bank_id` is required and must differ from the source; destination bank must exist and also have a linked GL account; `amount` must be a valid positive number.
4. **RECEIPT/PAYMENT**: at least 1 split is required; resolve and validate every split's account **before** writing anything (all-or-nothing — do not create partially-written state if one split account is invalid); every split amount must be a valid positive number; `total_amount = sum(split amounts)`.
5. `reference = reference or generate_bank_transaction_reference()` (§4.8).
6. Create a `POSTED` journal entry, `entry_type='BANK_TRANSACTION'`, `created_by=approved_by=<acting user>`, `approved_at=now`, `total_debit=total_credit=total_amount`:
   - TRANSFER: one CREDIT line on source's GL account, one DEBIT line on destination's GL account.
   - RECEIPT: one DEBIT line on the bank's GL account (source), one CREDIT line per split (against each split's account).
   - PAYMENT: one CREDIT line on the bank's GL account, one DEBIT line per split.
7. Create the `bank_transactions` row, linking `source_bank`, `destination_bank` (transfer only), the new `journal_entry`, and `vendor_id`/`customer_id` if supplied and they resolve to real records.

### 4.8 Atomic reference counters
Two counters must be race-safe (implemented as an atomic `UPDATE ... RETURNING` or an explicit transaction with `INSERT ... ON CONFLICT DO UPDATE`, mirroring the original's Cypher `MERGE ... ON CREATE / ON MATCH` counter-node pattern):
- **Bank transaction reference**: `bank_txn_counters` keyed by current year; `f"BT-{year}-{seq:04d}"`.
- **Invoice settlement reference** (fixes the historical duplicate-reference bug on partial payments): `invoice_settlement_counters` keyed by `(prefix, invoice_number)` where `prefix` is `"APPay"` or `"ARRec"`; `f"{prefix}-{invoice_number}-{seq:04d}"`. This guarantees every partial payment/receipt against the same invoice gets a distinct journal-entry reference, even though multiple partial payments share the same invoice.

By contrast, account codes (§4.1), journal manual references (§4.2), and invoice numbers (§4.9) use a non-atomic max-then-increment scan — replicate that distinction faithfully; do not make them all atomic.

### 4.9 AP invoice lifecycle
**Invoice number**: auto `f"PI-{year}-{seq:04d}"` if blank, via non-atomic scan of existing numbers starting with `f"PI-{year}-"`.

**Post** (`status` must be `DRAFT`, ≥1 line, must have an `ap_account` linked): `total = round(sum(line.amount), 2)`. Create a `POSTED` journal entry, `reference=f"AP-{invoice_number}"`, `entry_type='AP_PAYMENT'` (reused for the invoice-posting entry type too — not a separate value), DEBIT each line's `expense_account` for that line's amount (every line must have an expense account, or reject), CREDIT `ap_account` for the total. Set invoice `status='POSTED'`, `total_amount=total`.

**Void** (`status` must be `DRAFT` or `POSTED` — **not** `PAID` or already `VOID`): if it was `POSTED`, also void its linked journal entry. Set invoice `status='VOID'`. Does **not** touch `amount_paid` or unlink existing payments — a fully or partially paid invoice cannot be voided at all (blocked by the status check), which is intentional.

**Record payment** (`status` must be `POSTED`):
1. `remaining = round(total_amount - amount_paid, 2)`.
2. Overpay guard: if `amount > remaining + 0.01`, reject ("Payment amount {amount} exceeds remaining balance {remaining}."). The `0.01` slack absorbs float rounding, not a real allowance to overpay.
3. Bank account must exist and have a linked GL account.
4. Create a `POSTED` journal entry: `reference = generate_invoice_settlement_reference('APPay', invoice_number)` (§4.8), `entry_type='AP_PAYMENT'`, DEBIT `ap_account`, CREDIT bank's GL account, both for `round(amount, 2)`.
5. Create the `ap_payments` row, linking invoice/bank/journal entry.
6. Also create a `bank_transactions` row via §4.7's creation path (`transaction_type='PAYMENT'`, linking the invoice's vendor if present) — payments are unified with the bank transaction ledger.
7. `invoice.amount_paid += round(amount, 2)`. If `amount_paid >= total_amount - 0.01`, flip `status='PAID'`.

### 4.10 AR invoice lifecycle
Mirror of §4.9 with roles reversed:
- Invoice number `f"SI-{year}-{seq:04d}"`.
- **Post**: DEBIT `ar_account` for the total, CREDIT each line's `revenue_account`. Reference `f"AR-{invoice_number}"`, `entry_type='AR_RECEIPT'`.
- **Void**: identical status-machine rule to AP.
- **Record receipt**: same remaining/overpay math (`amount_received` instead of `amount_paid`); journal entry DEBITs the bank GL, CREDITs `ar_account`; reference via `generate_invoice_settlement_reference('ARRec', invoice_number)`; also creates a `bank_transactions` row (`transaction_type='RECEIPT'`, links customer if present); flips to `PAID` at the same `>= total - 0.01` threshold.

### 4.11 `AccountType` enum and normal-balance rule
Exact 10 values (string, not integer codes):
```
Sales, Cost of Sales, Expenses, Income Tax, Non-Current Assets, Current Assets,
Current Liabilities, Non-Current Liabilities, Owner's Equity, Other Incomes
```
Debit-normal set: `{Cost of Sales, Expenses, Income Tax, Non-Current Assets, Current Assets}`. Every other type (`Sales`, `Current Liabilities`, `Non-Current Liabilities`, `Owner's Equity`, `Other Incomes`) is credit-normal. **The UI computes `normal_balance` from the chosen type and sends it as an explicit field** — the business logic layer does not derive it server-side from `account_type` independently; it validates whatever `normal_balance` value is submitted as a required, independent field (so the UI computing it correctly is load-bearing — reproduce the same client-side derivation wherever an account is created: main Chart of Accounts form and the account quick-create modal inside the account-select widget, §7.1).

### 4.12 Bank reconciliation
**Toggle a line** (`bank_reconciliations.status` must be `DRAFT`, else reject "Cannot modify a completed reconciliation."): if a `reconciliation_lines` row for `(reconciliation_id, journal_line_id)` exists, delete it (un-reconcile); otherwise insert it (reconcile). Return the new `is_reconciled` state.

**Get GL lines for a bank/reconciliation**: fetch every `POSTED` journal line affecting the bank's linked GL account, ordered by entry date ascending; when scoped to a specific reconciliation, flag each line's `is_reconciled` based on whether a `reconciliation_lines` row exists for it.

**Complete** (`status` must currently be `DRAFT`, else reject "Already completed."):
```
book_balance = bank_account.opening_balance
             + SUM(amount) over reconciled lines where side='DEBIT'
             - SUM(amount) over reconciled lines where side='CREDIT'
diff = statement_balance - book_balance
if abs(round(book_balance,2) - round(statement_balance,2)) > 0.01:
    reject: f"Unreconciled difference of ₦{diff:,.2f}. Tick all matching items first."
else:
    status = 'COMPLETED'; completed_at = now
```
Completing is one-way — there is no "reopen" action anywhere in the product.

### 4.13 CSV bank statement import
Endpoint-equivalent inputs: `bank_account_id` (required), `default_account_id` (required — every imported row posts against this single GL account), a CSV `file` (required), optional `date_format` (`'dd/mm/yyyy'` default | `'mm/dd/yyyy'` | `'yyyy-mm-dd'` — unrecognized value silently falls back to `dd/mm/yyyy`), optional `date_range_type` (`'ALL'` default | `'DATE_RANGE'`) with `date_from`/`date_to` when ranged.

Parsing: decode the file as `utf-8-sig` (strip BOM). **Required exact column headers, case-sensitive: `Date`, `Description`, `Amount`.** Row numbering starts at 2 (row 1 is the header). Per row:
- A row with both an empty date and empty amount is silently skipped without incrementing any counter (treated as a trailing blank row).
- Unparseable date (per the selected format) → error `f'Row {i}: invalid date "{date_str}"'`, counted in `skipped`.
- Amount parsed as `float(amount_str.replace(',', ''))` (strips thousands separators); unparseable → error, counted in `skipped`.
- Amount of exactly `0` → silently skipped, counted in `skipped`, **no** error message logged for this case specifically.
- If date-range filtering is active and the row's date falls outside `[date_from, date_to]` → silently skipped, no error message.
- Sign determines transaction type: `amount > 0 → RECEIPT`, `amount < 0 → PAYMENT`.
- Every surviving row becomes **one** bank transaction via §4.7, with a single split: `{account_id: default_account_id, amount: abs(amount), description: ''}` — there is no per-row account mapping/categorization in v1.
- Any exception raised while creating a row's transaction is caught, appended to the error list, and also counted in `skipped` (not `created`).

Result reported to the user: `{created: int, skipped: int, errors: [str, ...]}`.

### 4.14 Budget lifecycle & variance
**Create**: requires ≥1 line; the same `account_id` may not appear on more than one line of the same budget — reject otherwise.

**Approve** (must not already be `APPROVED`, else reject "Already approved."): set `approved_by`, `approved_at=now`, `status='APPROVED'`.

**Delete**: reject with "Cannot delete an approved budget." if `status='APPROVED'`.

**Variance** (per line): for each budget line's account, sum all `POSTED` journal lines affecting it — **no date filtering at all**, the actual figure is the account's entire all-time POSTED history, not scoped to the budget's `fiscal_year` text field. `actual = debits - credits` if debit-normal, else `credits - debits`. `variance = round(budgeted - actual, 2)`. `variance_pct = round(variance / budgeted * 100, 1)` if `budgeted != 0`, else `None`/blank.

### 4.15 Financial reports
Shared helper: `_account_balance(normal_balance, debits, credits)` = debits−credits if DEBIT-normal else credits−debits, rounded to 2dp. All four reports only ever include accounts with `is_active=1`.

**Trial Balance** (`date_from`, `date_to` both required): for every active account, sum POSTED debits/credits within `[date_from, date_to]` inclusive, compute `balance`. On-screen/JSON: shows raw `total_debits`/`total_credits` per row plus aggregate totals. **PDF/XLSX export nets each row down to a single debit-or-credit column**: `display_debit = max(0, total_debits - total_credits)`, `display_credit = max(0, total_credits - total_debits)`, with a totals row summing the netted columns (not the raw ones) — replicate this on-screen too, since the Angular UI performs the exact same netting client-side for the on-screen table (see §6.12).

**Income Statement** (`date_from`, `date_to` required): buckets active accounts by type into Revenue (`Sales`, `Other Incomes`), Cost of Sales (`Cost of Sales`), Expenses (`Expenses`, `Income Tax`), each row's `balance` computed as above within the date range. `gross_profit = total_revenue - total_cos`. `net_surplus = gross_profit - total_expenses`.

**Balance Sheet** (`as_of_date` only — single date, no lower bound, cumulative from all time): buckets into Assets (`Non-Current Assets`, `Current Assets`), Liabilities (`Current Liabilities`, `Non-Current Liabilities`), Equity (`Owner's Equity`). Additionally computes the Income Statement over the entire history (`date_from='0001-01-01'` through `as_of_date`) and, **if `net_surplus != 0`**, appends a synthetic equity row `{code:'', name:'Profit/(Loss) — current & prior periods', account_type:"Owner's Equity", balance: net_surplus}` — this is a **live, recomputed-every-time** rollup, not a posted closing entry; there is no period-closing mechanism in this product. `is_balanced = abs(total_assets - (total_liabilities + total_equity)) < 0.01`.

**GL Detail** (`account_id`, `date_from`, `date_to` all required): fetch the account; all POSTED lines in range ordered by entry date ascending then reference ascending; compute a running balance per line, `+= amount` when the line's side matches the account's normal-balance side, else `-= amount`. Returns each line plus a final `closing_balance`.

**Dashboard** (no params, all-time, no date filter): sum balances of all active Asset accounts → `total_assets`; all active Liability accounts → `total_liabilities`; `net_equity = total_assets - total_liabilities`. AP/AR outstanding: sum `(total_amount - amount_paid)` over purchase invoices with `status='POSTED'`, and the AR equivalent for sales invoices with `status='POSTED'` — **replicate the original's filter exactly as `status IN ('POSTED','PARTIAL')` even though `'PARTIAL'` is never a real status value** (see §10 — this is intentionally a no-op extra condition, not a bug to complete by inventing a PARTIAL status). `recent_entries`: the 10 most-recently-dated POSTED journal entries (tie-broken by `created_at` descending), each showing reference/description/date/total_debit.

### 4.16 Export/print mechanics
- **PDF**: rendered from the same data each report/list screen already displays, one PDF template-equivalent per document type (trial balance, income statement, balance sheet, purchase invoice, sales invoice, account list, vendor list, etc.) — see §8 for the exact column sets. Purchase/sales invoice PDFs additionally show `settled_amount` (= amount_paid/amount_received) and `outstanding_amount` (= `max(0, total - paid)`).
- **XLSX**: `openpyxl` workbook, bold header row, one sheet per export.
- **CSV**: bank transaction export only supports CSV as an additional format alongside XLSX.

---

## 5. Auth & RBAC Spec

### 5.1 Local session model
There is no network, so there is no JWT. On launch, show a login screen; on successful username/password check (PBKDF2 verify), hold the authenticated user (id, username, resolved group names) in an in-memory application-level session object for the lifetime of the running app. Logging out clears that in-memory session and returns to the login screen. **There is no token-expiry/auto-logout timer** — the original's 8h access / 7d refresh JWT lifetimes existed to bound a networked session's risk window; a local single-machine app has no equivalent network-exposure concern, so persistent login-until-explicit-logout is the correct, deliberate simplification (documented here, not a missed requirement).

### 5.2 Registration flow
Invite-code-gated self-registration, reproduced exactly:
1. `invite_code` must exist and have `status == 'active'` (i.e., not used, not expired) — else reject "Invalid or expired invite code."
2. `username` and `password` required; `password == confirm_password` required; `password` must be ≥ 8 characters; `username` must not already exist; if `email` given, it must not already be registered to another user.
3. Create the user; add them to a get-or-create **`Staff`** group (self-registered users never get Admin/Manager/Accountant automatically).
4. Mark the invite code used: `used_by`, `used_at=now` (this is what makes it single-use).
5. Show a success confirmation — **do not auto-login**; the user must return to the login screen and sign in separately.

### 5.3 Permission matrix (reproduce exactly — do not tighten or loosen)
| Action | Required role |
|---|---|
| Create/edit an Account | Admin or Manager |
| Delete an Account | Admin only (and blocked entirely if `is_system=1`, regardless of role) |
| Create a Fiscal Year | Admin only |
| Delete a Budget | Admin only |
| Generate/revoke an Invite Code | Admin or Manager (or a Django-style "is_staff" superuser-equivalent flag, if you choose to model one) |
| **Everything else** — create/edit/delete Vendors, Customers, Items, Bank Accounts; create/post/void Journal Entries; create/post/void/pay/receive AP & AR invoices; create Bank Transactions; toggle/complete Bank Reconciliations; approve Budgets | **Just being logged in — no group check at all.** |

This last row is intentional fidelity, not an oversight in this PRD: the live system genuinely has no role gate on posting/voiding journal entries or invoices, paying/receiving, reconciling, or approving budgets. Reproduce that.

### 5.4 UI-level gating quirk (reproduce exactly)
On 5 of the original screens (journal entry detail, both AP/AR invoice detail screens, bank reconciliation, budget detail), the button-visibility check that *looks* like a Manager/Admin role check is actually implemented as "is anyone logged in at all" — so Post/Void/Approve/Complete-Reconciliation/Edit-Draft/Delete-Draft buttons are visible to **every** authenticated user (including `Staff`) on those five screens, regardless of role. Only the **journal entry form's** "Save & Post" button implements a genuine Manager/Admin role check. Reproduce this exact per-screen split (§10 has the full list) — do not unify it into one consistent rule.

---

## 6. UI/UX Spec — Screen by Screen

General conventions applying to every list screen unless noted otherwise:
- Client-side pagination: fetch the full result set once, paginate in-memory at **25 rows/page**; page resets to 1 whenever a tab or filter changes; the pager control only renders when total rows > page size.
- Every monetary value displayed as `₦#,##0.00`.
- Every export action offers PDF and/or XLSX (bank transactions additionally offer CSV) as a file-save dialog (native Windows save dialog, since there's no browser download flow to emulate).

### 6.1 Login
Split layout: a dark navy branding panel (wordmark "Page", "Topfaith University / Finance System" subtitle, "Accounting · Reporting · Compliance" footer) beside a form panel. Fields: Username, Password (with show/hide toggle). "Forgot password?" navigates to a static informational screen (§6.3). On success, land on the **Chart of Accounts** screen (not the dashboard — replicate this exact destination). On failure: "Invalid username or password." Loading state disables the submit button and shows "Signing in…". Link to Sign Up.

### 6.2 Sign Up
Same branding layout. Fields: Username* , Email (optional), Password* (min 8 chars, show/hide), Confirm Password* (must match — checked before submit), Invite Code* (masked, show/hide). On success, show an inline success state ("Account created — set up with a Staff role. Sign in to get started.") with a button to go to Login; **no auto-login**. On error, surface the server-equivalent validation message (invalid/expired code, username taken, password too short, passwords don't match, email taken).

### 6.3 Forgot Password
Static informational screen only, no logic: "Password resets are managed by your system administrator — contact them directly." Links back to Login and to Sign Up.

### 6.4 App Shell
Persistent left sidebar (dark navy) + main content area, shown for every screen once logged in. Sidebar sections, exactly in this order, each a collapsible accordion except Dashboard which is a flat top-level link:
1. **Dashboard** (flat link)
2. **Ledger** (open by default): Chart of Accounts, Journal Entries
3. **Banking**: Bank Accounts, Transactions, Import Statement
4. **Reports**: Trial Balance, Income Statement, Balance Sheet, GL Detail
5. **Payables**: AP Invoices, Items, Vendors
6. **Receivables**: AR Invoices, Customers
7. **Budget**: Budgets
8. **Administration** — **only rendered if the logged-in user is Admin or Manager**: Invite Codes

Footer: Sign Out. Unmatched/fallback navigation lands on **Chart of Accounts** (not Dashboard — same as the original's wildcard route), and Dashboard is otherwise reachable only via its own sidebar link.

### 6.5 Dashboard
One data load on entry. No charts — plain KPI cards only:
- 3 top cards: Total Assets, Total Liabilities, Net Equity (₦, large monospace figures).
- 2 cards: AP Outstanding (links to AP Invoices list), AR Outstanding (links to AR Invoices list).
- "Recent Posted Entries" list (the 10 from §4.15): reference, description, date, total debit; each row navigates to that entry's detail screen; "View all" link to Journal Entries list. Empty state: "No posted entries yet."

### 6.6 Chart of Accounts — List
Header with Export PDF/XLSX + "+ New" (visible to any logged-in user per §5.3) toggling an inline create/edit panel (not a separate screen/dialog): Name*, Type* (dropdown of the 10 `AccountType` values), Description, and a **read-only** Normal Balance preview computed live from the chosen type (§4.11). Table columns: Code, Name (navigates to detail), Type, Normal Balance, Balance (colored: normal color if ≥0, danger color if negative), Actions (Edit for any logged-in user; **Delete only for Admin**). Delete asks for confirmation first. Empty state prompts to create the first account.

### 6.7 Chart of Accounts — Detail
Loads the account then its ledger (§4.15/§4.5's ledger fetch — all POSTED lines affecting it). Header shows "{code} — {name}" and a back link. Info card: Type, Normal Balance, Code, and a large highlighted Current Balance. Ledger table: Date, Reference, Description, Entry Type (badge — see §7.3's entry-type badge colors), Side (DEBIT/CREDIT, colored), Amount. Empty state: "No posted ledger entries for this account."

### 6.8 Journal Entries — List
Tabs: ALL / DRAFT / POSTED / VOID, re-fetching filtered by status on change (resets to page 1). Export PDF/XLSX + "+ New Entry". Table: Reference, Date, Description, Debit, Credit, Status (colored text, not a badge pill, per §7.3 System C). Rows navigate to detail.

### 6.9 Journal Entry — New/Edit form
Date field (defaults today). A repeatable list of "rows", each with: From Account (debited) — the account-select widget (§7.1), Amount (min 0.01), To Account (credited) — account-select, optional line Description; a remove-row control (disabled when only one row remains); "+ Add line". A footer bar shows the running Total (sum of all row amounts) and a readiness indicator: "✓ Ready" when every row has both accounts and a positive amount, else "✗ Incomplete". On submit, each valid row expands into one DEBIT line (from account) + one CREDIT line (to account) as described in §4.3; the entry description is server-derived, not directly entered by the user on this form (the per-row description fields feed into it). Two submit actions: **Save as Draft** (always available, creates/updates status `DRAFT`) and **Save & Post** (only rendered for a real Admin/Manager check per §5.4 — creates/updates *and* immediately posts, landing on the detail screen). Both disabled until the form is valid and balanced. In edit mode, only `DRAFT` entries are editable; the existing lines must be reconstructed into from/to rows by pairing DEBIT and CREDIT lines by their position in the entry (this pairing heuristic can misrepresent entries whose debit/credit line counts don't naturally pair 1:1 — reproduce the same limitation, do not build a smarter reconciliation).

### 6.10 Journal Entry — Detail
Header: reference + status (plain colored text). Action buttons, gated per §5.4's loose "any logged-in user" check on this screen: "Edit Entry"/"Delete Draft" (shown only when status is `DRAFT`), "Post Entry" (shown when `DRAFT`), "Void Entry" (shown when `POSTED`, confirms first with "Void this entry? This cannot be undone."). Info card: Date, Type, Created by, Description. Lines table: Account (code — name), Side (colored), Amount, Memo; footer Total row.

### 6.11 Banking — Bank Accounts List
Export PDF/XLSX + "+ New" inline form: Account Name*, Account Number, Bank Name*, Opening Balance, Opening Balance Date* (defaults today), GL Account (account-select, optional — linking one enables balance computation). Table: Name (→ detail), Bank, Account No., Opening Balance, Current Balance (dash if no GL linked; red if negative), Actions (View always; Edit/Delete for any logged-in user).

### 6.12 Bank Account — Detail
Loads the account plus its reconciliations list. Header: name, "+ New Transaction" (pre-fills the source bank on the transaction form), "+ New Reconciliation" toggle (visible on the Reconciliations tab). Info card includes a highlighted Current Balance (shows "— (no GL account linked)" if unlinked). Two tabs: **Reconciliations** (default — table of period range, statement balance, status colored COMPLETED/green, DRAFT/amber, else gray; created-by; rows navigate to the reconciliation screen) and **Transactions** (lazily loaded on first click — reference, date, type colored RECEIPT/green PAYMENT/red TRANSFER/blue, description, amount). New-reconciliation inline form: Period Start*, Period End*, Statement Balance*.

### 6.13 Bank Transactions — List
Filter bar: Bank (bank-select), From date, To date — any change re-queries and resets pagination; "Clear" resets all three. Export CSV/XLSX (filters included in the export request). "↑ Import Statement" toggles an **inline** CSV-import panel with the same fields/behavior as the standalone Import screen (§6.15) — both are present in the product and both call the same import logic; this duplication is intentional to preserve (§10), not something to consolidate. "+ New Transaction" link to the multi-row entry form. Table: Reference, Date, Bank, Type (colored badge), Description, Amount.

### 6.14 Bank Transaction — New (multi-row entry form)
A register-style form supporting several heterogeneous rows submitted together. Top-level: Source Bank Account* (bank-select; pre-filled if arriving from a bank's detail screen). A repeatable Rows list, each row:
- Date* (defaults today), Description, **Type** selector: `LEDGER` | `BANK` | `SUPPLIER` | `CUSTOMER` — determines which selection control appears next; changing Type clears the row's selection fields.
- Selection column by Type:
  - `LEDGER`: account-select.
  - `BANK`: bank-select restricted to exclude the source bank (for inter-bank transfers).
  - `SUPPLIER`: vendor-select; once a vendor is chosen, fetch that vendor's `POSTED` purchase invoices and, if any exist, show a dropdown of them (label: invoice number + remaining amount due) plus a "— Miscellaneous (no invoice) —" option; if no invoice is selected, also show an account-select for a contra GL account.
  - `CUSTOMER`: mirrors SUPPLIER via customer-select and that customer's `POSTED` sales invoices (remaining = total − amount_received).
- Reference (optional, "Auto" placeholder when left blank), a mutually-exclusive **Spent** / **Received** amount pair (entering one clears the other), and a remove-row control (disabled if only one row remains).

Row validation before submit: date required; exactly one of Spent/Received > 0; `BANK` rows require a destination bank; `LEDGER` rows require an account; `SUPPLIER`/`CUSTOMER` rows require the party plus either a selected invoice or a contra account.

Submit ("Post All") validates every row first, aggregating all row errors into one combined message before submitting anything; then submits rows **sequentially** (not in parallel), collecting a per-row success/failure result; only navigates back to the Transactions list if every row succeeded. Row-level routing on submit:
- If a row has a selected invoice, route it through the AP-pay / AR-receive logic (§4.9/§4.10) instead of the generic bank-transaction path, so invoice history stays in sync.
- Otherwise route through §4.7's generic transaction creation: `BANK`+Spent → TRANSFER out; `BANK`+Received → TRANSFER in (roles swapped); `SUPPLIER` → PAYMENT/RECEIPT with a single split against the contra account, tagged with the vendor; `CUSTOMER` → mirror, tagged with the customer; `LEDGER`/default → PAYMENT/RECEIPT with a single split against the chosen account.

### 6.15 Bank Statement Import (standalone screen)
Fields: Bank Account*, Default GL Account*, Import File Type (CSV only, shown as a fixed dropdown), Date Format (dd/mm/yyyy | mm/dd/yyyy | yyyy-mm-dd), a file picker restricted to `.csv`, a Date Range toggle (All Transactions vs. a From/To pair). "Import File" is disabled until all required fields are set. On submit, run §4.13 and show: a Created count, a Skipped count, a Row Errors list (if any), and a link to the Transactions list when `created > 0`.

### 6.16 Bank Reconciliation screen
Header: status pill (COMPLETED green / DRAFT amber / other gray). Info card: bank account name, period, statement balance. GL Lines table: date, reference, description, side, amount, and a **Reconciled** checkbox per row (row highlighted when checked); checkboxes disabled once the reconciliation is `COMPLETED`. Toggling a checkbox calls §4.12's toggle. A live-computed summary panel (recomputed client-side from the currently-reconciled lines, not re-fetched): Opening Balance, Reconciled Debits, Reconciled Credits, Book Balance, Statement Balance, Difference, and a readiness message ("✓ Ready to complete" vs. "Tick matching items above until the difference reaches ₦0.00."). "Complete Reconciliation" is shown (per §5.4's loose gate) only while `DRAFT`, disabled until the difference is within tolerance.

### 6.17 Payables — AP Invoices List
Tabs ALL/DRAFT/POSTED/PAID/VOID. Export PDF/XLSX + "+ New Invoice". Table: Invoice #, Date, Due Date, Vendor, Total, Paid (`amount_paid`), Status (badge, §7.3 System B colors). Empty state includes a "Create first invoice" call to action.

### 6.18 AP Invoice — New/Edit
Header fields: Date*, Due Date*, Vendor* (vendor-select), AP Account* (account-select), Description. Lines list (Item picker column only rendered if at least one Item exists in the system): optional Item picker that autofills the row (§6.20), Expense Account* (account-select), Description, Quantity* (min 0.01), Unit Price* (min 0), Amount* (auto-recomputed on qty/price change as `round(qty * unit_price, 2)`, but remains directly user-editable afterward — the recompute does not lock the field). Footer running Total. Only a **Save as Draft/Save Changes** action exists on this form — posting only happens from the detail screen, never from the form itself. Only editable while `DRAFT`.

### 6.19 AP Invoice — Detail
Loads the invoice plus all bank accounts. "Print PDF" always available. Per §5.4's loose gate: Edit/Delete/"Post Invoice" (all only while `DRAFT`), "Void" (while `DRAFT` or `POSTED`, confirmed first). Info card: Vendor, Date, Due Date, AP Account, Total, Remaining (`max(0, total-paid)`), Description. Lines table with a Total footer. **Record Payment panel** appears only while `status='POSTED'` **and** remaining > 0.005 (so it disappears the instant the invoice is fully paid): Payment Date* (defaults today), Amount* (min 0.01, **pre-filled with the full remaining balance** — the user may reduce it to make a **partial** payment), Reference (optional), Bank Account* (bank-select). On submit, reload the invoice fresh (status flips to `PAID` or stays `POSTED` with a smaller remaining, per §4.9's math) and re-prefill the amount field with the new remaining.

### 6.20 Item autofill pattern (shared by AP and AR invoice line forms)
Selecting an Item in the line's Item picker patches that line's fields: `expense_account_id` (AP) or `revenue_account_id` (AR) ← item's default account (blank if the item has none), `description` ← item's name, `unit_price` ← item's unit price (default 0), then recomputes `amount` from the current quantity (which is **not** overwritten by the item — it keeps whatever value it already had, default 1). The invoice line never stores a reference back to the Item; it's a one-time template copy.

### 6.21 Payables — Vendors List
"+ New Vendor" inline form (Name* only required; Email, Phone, Address optional). Export PDF/XLSX. Table: Name, Email, Phone, Actions (Edit/Delete for any logged-in user — no role gate).

### 6.22 Payables — Items List
"+ New Item" inline form: Name* required, Type (Service/Product, default Service), Unit Price (default 0), Preferred Vendor (vendor-select, optional), Default Expense Account (account-select, optional), Default Revenue Account (account-select, optional), Description. No export buttons on this screen. Table: Name, Type, Unit Price, Vendor (or dash), Expense Account (or dash), Revenue Account (or dash), Actions.

### 6.23 Receivables — mirror of §6.17–6.22
AR Invoices List (same tabs/columns but Customer + Received=`amount_received`), AR Invoice New/Edit (Customer*, AR Account*, revenue-account lines), AR Invoice Detail ("Record Receipt" panel, same partial-receipt UX), Customers List (Name* required; Type = External/Student default External; Email, Phone).

### 6.24 Budget — List
Export PDF/XLSX + "+ New Budget". Table: Name, Fiscal Year, Total Budgeted, Status (colored text: APPROVED green, DRAFT amber), Created By.

### 6.25 Budget — New
Budget Name*, Fiscal Year* (free-text field, e.g. "2025/2026" — not a date picker or dropdown). Lines list: Account* (account-select), Annual Budget* (min 0.01). Footer running Total. "Save as Draft" only — **there is no edit screen for an existing budget**; budgets are create-once (lines can't be changed after creation in v1, matching the original which never exposes a PATCH/update for budgets).

### 6.26 Budget — Detail
Header: Name, Fiscal Year, Status. "Approve Budget" shown (per §5.4's loose gate) while `DRAFT`. Two tabs: **Budget Lines** (default — Account, Type, Annual Budget, Total footer) and **Variance Report** (lazily computed on first visit, then cached for the rest of the screen's lifetime — Account, Budget, Actual, Variance (colored green ≥0 / red <0), Variance % (or a dash when `budgeted=0`)).

### 6.27 Admin — Invite Codes
Only reachable by Admin/Manager (self-guards on entry — a non-Admin/Manager user landing here directly should be bounced back to Chart of Accounts, same destination as §6.1's post-login landing). "+ Generate Code" creates a new 7-day-TTL code and prepends it to the active list. **Active codes** shown as a card grid: code value, "Created by X · Expires {date}" meta line, a "Copy" action (copies to clipboard, shows a transient "✓ Copied" confirmation for ~2 seconds) and a "Revoke" action (deletes the code — blocked with an error if it's already used). Empty state for no active codes. **History table** (used + expired codes, only shown if any exist): Code, Status badge (Used/Expired), Created By, Used By (dash for expired), Expires. Dates formatted `DD Mon YYYY` (e.g. "15 Jul 2026").

### 6.28 Reports — Trial Balance
Filters: From*, To* (both required before "Run Report" enables). Rows are grouped by `account_type` into visually separated sections (assumes accounts are pre-sorted by code, which naturally clusters by type-prefix). Each row nets to a single debit-or-credit column per §4.15's PDF/XLSX netting rule — apply that same netting to the on-screen table too, with a grand-totals footer row summing the netted columns.

### 6.29 Reports — Income Statement
Filters: From*, To*. Sections in this fixed order: Revenue (+ Total Revenue subtotal), Cost of Sales (+ Gross Profit subtotal), Expenses (+ Total Expenses subtotal), then a "Net Surplus / (Deficit)" footer row, colored green/positive-styling if ≥0, red/negative-styling if <0.

### 6.30 Reports — Balance Sheet
Filter: As of Date* only (single date). Sections: Assets, Liabilities, Equity (including the synthetic Profit/(Loss) rollup row from §4.15 when non-zero), each with a subtotal. Footer banner: green "Assets = Liabilities + Equity (balanced)" when `is_balanced`, else a red warning "Balance sheet does not balance — check for unposted entries." Includes an extra "Type" column not present on the Income Statement.

### 6.31 Reports — GL Detail
Filters: Account* (account-select), From*, To* — all required. Summary strip showing the account code/name and the date range. Table: Date, Reference, Description, Entry Type (badge), Side (colored), Amount, and a bold **Running Balance** column (server/business-logic computed per §4.15, displayed as-is — no client recomputation). Footer: Closing Balance.

---

## 7. Shared Components

### 7.1 "Smart select" widgets (Account, Bank, Vendor, Customer, Item)
One reusable Flet pattern, instantiated five times with per-entity config. Behavior, identical across all five:
- A text field showing a human-readable label for the current selection (e.g. "1000 — Cash at Bank" for accounts, "Vendor Name" for vendors). Typing filters the full in-memory list of that entity (case-insensitive substring match against: name+code for accounts, name+bank_name for banks, name+email for vendors/customers, name for items) and opens a dropdown of matches below the field.
- If the typed text no longer exactly matches the currently-selected item's label, the selection is cleared (typing away from a valid choice invalidates it — this is deliberate, not a bug to smooth over).
- The dropdown's first row is always a pinned **"+ Create {entity}…"** action, visually separated from the results below it, opening an inline quick-create dialog.
- An empty-results row reads `No {entities} match "{search text}"`.
- Clicking outside the widget closes the dropdown.
- **Quick-create dialog fields per entity** (submit disabled until the marked-required fields are filled):
  - **Account**: Name* (pre-filled from the current search text, unless that text looks like an already-formatted "code — name" label, in which case start blank), Type* (dropdown), a read-only computed Normal Balance preview (§4.11), Description.
  - **Bank Account**: Account Name* (pre-filled from search text) + Bank Name*, Account Number + Opening Balance, Opening Balance Date* (defaults today), GL Account (a nested account-select — the widget must support being used inside another instance of itself).
  - **Vendor**: Name* (pre-filled), Email, Phone, Address.
  - **Customer**: Name* (pre-filled), Type (dropdown, default External), Email, Phone.
  - **Item**: Name* (pre-filled), Description, Unit Price (default 0), Type (dropdown, default Service). The Item widget is used slightly differently from the other four: it does not bind directly to a form field's value — it's used purely to drive the §6.20 autofill via a "picked" event, while the actual invoice-line fields it patches are separate, independently bound controls.
- On successful creation: append the new record to the shared in-memory list for that entity type (so every other instance of the same widget on the same screen picks it up), and auto-select the newly created record into the field that opened the dialog.
- **Bank-select specific**: supports an "exclude this id" parameter (used on the multi-row bank transaction form to hide the source bank from the destination-bank list when Type=BANK).

### 7.2 Pagination
25 rows/page everywhere; full result set fetched/loaded once, sliced client-side; pager only rendered when the total exceeds the page size; changing any filter/tab resets to page 1.

### 7.3 Status color systems (reproduce all three, per-screen, exactly as assigned above — do not unify them into one palette)
**System A — pill badges** used for invoice status (§6.17/§6.23) and generic status badges elsewhere:
```
DRAFT:    bg #F3F4F6, text #6B7280 (gray)
POSTED:   bg #EFF6FF, text #1D4ED8 (blue)
PAID:     bg #F0FDF4, text #15803D (green)
VOID:     bg #FFF1F2, text #B91C1C (red)
```
Pill styling: inline-block, small padding, 4px radius, 12px bold uppercase text with slight letter-spacing.

**System B — plain colored text** (no pill) used for journal entry status, invoice-detail headers, bank reconciliation status pill, budget status, bank-transaction type, and budget variance sign:
```
Journal entry:      DRAFT #f59e0b   POSTED #10b981   VOID #ef4444
Invoice header:      DRAFT #f59e0b   POSTED #1a73e8   PAID #10b981   VOID #ef4444
Bank reconciliation: COMPLETED #10b981   DRAFT #f59e0b   other #888888
Bank txn type:       RECEIPT #10b981   PAYMENT #ef4444   TRANSFER #3b82f6
Budget:              APPROVED #10b981   DRAFT #f59e0b
Budget variance:     >= 0 → #10b981 (favorable)   < 0 → #ef4444 (unfavorable)
```

**GL/ledger entry-type badges** (account detail ledger, GL Detail report):
```
MANUAL:            bg #F3F4F6, text #6B7280
BANK_TRANSACTION:  bg #EFF6FF, text #1D4ED8
AP_PAYMENT:        bg #FFF7ED, text #C2410C (orange)
AR_RECEIPT:        bg #F0FDF4, text #15803D
(default fallback = MANUAL style)
```

### 7.4 Design tokens
```
Colors:
  navy-deep:      #10002B   (sidebar background, headings)
  navy-primary:   #314991   (primary buttons, links, table header background)
  navy-mid:       #3D5BA8   (primary button hover)
  navy-light:     #EEF2FF
  navy-subtle:    #F0F4FB   (app canvas background, row stripe/hover)
  purple:         #6F448D
  purple-dark:    #5A3575
  purple-light:   #F3EEF8
  purple-mid:     #9B72B8   (active-nav-link accent border, wordmark accent)
  success:        #15803D / bg #F0FDF4 / border #BBF7D0
  warning:        #B45309 / bg #FFFBEB / border #FDE68A
  danger:         #B91C1C / bg #FEF2F2 / border #FECACA
  border:         #DDE3F0 (strong: #C5CDE8)
  text-primary:   #10002B
  text-secondary: #3D4B77
  text-muted:     #7B87B0
Fonts: DM Serif Display (headings/wordmark), Mulish (body/UI text), JetBrains Mono (numbers/codes/monetary values)
Radii: xs 4px, sm 6px, md 8px, lg 12px, xl 16px
```
Since the app is fully offline, **bundle the three font families as local files inside the app package** rather than loading them from Google Fonts — this is a required adaptation, not optional polish, or the entire typography system silently falls back to system defaults.

Report table headers use a slightly different near-black `#1a1a2e` rather than `navy-primary` — an existing inconsistency, reproduce it rather than "fixing" it to match the rest of the app (§10).

---

## 8. Export/Print Column Reference

| Export | Columns |
|---|---|
| Accounts | Code, Name, Type, Normal Balance, Balance (N) |
| Journal Entries | Reference, Date, Description, Debit (N), Credit (N), Status |
| Bank Accounts | Name, Bank, Account No., Opening Balance (N), Current Balance (N) |
| Bank Transactions | Reference, Date, Bank, Type, Description, Amount |
| Purchase (AP) Invoices | Invoice #, Vendor, Date, Due Date, Total (N), Paid (N), Status |
| Sales (AR) Invoices | Invoice #, Customer, Date, Due Date, Total (N), Received (N), Status |
| Vendors | Name, Email, Phone |
| Customers | Name, Type, Email, Phone |
| Budgets | Name, Fiscal Year, Total Budgeted (N), Status, Created By |
| Trial Balance | Account, Debit (N) [netted], Credit (N) [netted], with a Totals row |
| Purchase/Sales Invoice print (PDF) | full line detail plus Total, Settled Amount, Outstanding Amount |

All XLSX exports: bold header row. All exports sorted the same way their on-screen list is sorted unless the export view says otherwise (accounts sorted by code).

---

## 9. Non-Functional Requirements

- **Fully offline**: no network calls anywhere in the running app.
- **Single SQLite file per install**: created on first launch if absent; no external DB service.
- **Currency formatting**: `₦#,##0.00` everywhere monetary values are shown.
- **Local time only**: no timezone conversion; the machine's wall clock is authoritative.
- **Packaging**: one Windows `.exe` (or installer) via `flet build windows`/PyInstaller, bundling Python, all dependencies, fonts, and the app's static resources — nothing downloaded at runtime.
- **Performance target**: smooth interaction (list loads, exports, report generation) at classroom-scale data volumes — hundreds to low thousands of accounts/entries/invoices per install, not enterprise-scale.
- **No multi-user concurrency handling required**: SQLite's default locking is sufficient since only one instance of the app runs against one DB file at a time on one machine.

---

## 10. "Replicate As-Is" Quirks List (do not silently fix)

| # | Quirk | Where documented |
|---|---|---|
| 1 | `JournalEntry.period` / `AccountingPeriod` linkage is modeled but never populated anywhere; closing a period has no effect on posting. | §3.3, §4.4 |
| 2 | Account codes, manual journal-entry references, and invoice numbers are generated via a non-atomic max-then-increment scan (race-prone in theory); bank-transaction references and invoice-settlement references use a genuinely atomic counter. Keep this asymmetry. | §4.1, §4.2, §4.8, §4.9 |
| 3 | No role/group check at all on posting/voiding journal entries, posting/voiding/paying/receiving invoices, creating bank transactions, toggling/completing reconciliations, or approving budgets — only Account CRUD, Fiscal Year creation, Budget deletion, and Invite Code management are role-gated. | §5.3 |
| 4 | On 5 specific screens, the button-visibility check that reads as a Manager/Admin check is actually "any logged-in user"; only the journal-entry form's Save & Post button does a real role check. | §5.4 |
| 5 | The dashboard's AP/AR outstanding query filters invoice status by `IN ('POSTED','PARTIAL')` even though `'PARTIAL'` is never a valid invoice status — it's a permanently no-op extra condition, not a status to actually implement. | §3.5/3.6, §4.15 |
| 6 | Voiding a journal entry or invoice never reverses/rewrites amounts — it only excludes the entry from all POSTED-scoped balance/report queries going forward. | §4.4, §4.9, §4.10 |
| 7 | The Bank Statement Import feature exists as both a standalone screen and an inline panel on the Transactions list, calling identical logic — keep both, don't consolidate into one. | §6.13, §6.15 |
| 8 | Three separate, non-unified color systems exist for status display (pill badges, plain colored text, GL entry-type badges) and are used inconsistently per screen — reproduce the exact system used on each screen per §7.3, don't standardize on one. | §7.3 |
| 9 | Report table headers use a hardcoded near-black `#1a1a2e` instead of the `navy-primary` token used by every other data table in the app. | §7.4 |
| 10 | Budgets have no edit screen or update path after creation — only create, approve, and (if still DRAFT) delete. | §6.25 |
| 11 | The journal-entry edit form reconstructs "from/to" rows by positionally pairing DEBIT and CREDIT lines — this can misrepresent entries whose debit/credit line counts don't naturally pair 1:1. Don't build a smarter reconciliation for it. | §6.9 |

---

## 11. Out of Scope (v1)

- Any network sync between installs, or between this app and the existing web system.
- Email sending (invite codes, notifications, password resets) — invite codes are copy/pasted manually, as today.
- Real payment gateway integration.
- Any exam-specific seed-data, reset-to-scenario, or export-for-grading tooling (confirmed with the user as unnecessary — exam logistics are handled outside the app).
- Automated multi-user concurrency or cloud backup.
- Any change to the existing live Django/Angular/Neo4j system — this PRD describes a wholly separate artifact.
- Formal automated test suite requirements beyond whatever the build prompt (companion document) specifies for its own verification purposes.

---

## 12. Feature Parity Checklist (acceptance criteria)

Every item below must be present and behaviorally correct before this build is considered complete.

**Auth & Users**
- [ ] Login screen (username/password against local `users` table)
- [ ] Sign up screen (invite-code gated, §5.2 validation rules, Staff group assignment, no auto-login)
- [ ] Forgot Password static screen
- [ ] Logout clears session
- [ ] Invite Codes admin screen: generate (7-day TTL), copy, revoke (blocked if used), active/history split, self-guarded to Admin/Manager

**Chart of Accounts**
- [ ] List with export PDF/XLSX, inline create/edit, delete (Admin only, blocked for `is_system`)
- [ ] Auto code generation (§4.1) and code/opening-balance immutability
- [ ] Account types dropdown sourced from the 10-value enum; live normal-balance preview
- [ ] Detail screen with ledger and computed balance (§4.5)
- [ ] Idempotent opening-balance auto-posting (§4.6)

**Journal Entries**
- [ ] List with ALL/DRAFT/POSTED/VOID tabs, export
- [ ] New/Edit form: repeatable from/to rows → 2 lines each, running total, balance readiness indicator, auto description derivation
- [ ] Save as Draft vs. Save & Post (real role gate on Post)
- [ ] Detail: edit/delete draft, post, void (loose gate per §5.4), lines table
- [ ] Reference auto-generation (§4.2), balance validation (§4.3) enforced twice
- [ ] Posting/voiding rules exactly per §4.4

**Banking**
- [ ] Bank Accounts list/detail, opening-balance immutability, GL linkage, current-balance display
- [ ] Bank Transactions list with bank/date filters, export CSV/XLSX
- [ ] Multi-row transaction entry form with LEDGER/BANK/SUPPLIER/CUSTOMER row types and all routing rules (§6.14)
- [ ] Standalone + inline CSV import screens, both wired to §4.13's exact parsing/skip/error rules
- [ ] Bank Reconciliation screen: toggle lines, live summary panel, complete with ₦0.01 tolerance, one-way completion
- [ ] Atomic bank-transaction reference counter (§4.8)

**Payables**
- [ ] Vendors CRUD (name-only required)
- [ ] Items CRUD + autofill pattern into invoice lines (§6.20)
- [ ] AP Invoices list/new/edit/detail, print PDF, post/void/delete rules, Record Payment panel with partial-payment support and atomic settlement reference (§4.9)

**Receivables**
- [ ] Full mirror of Payables: Customers, AR Invoices, Record Receipt (§4.10)

**Budget**
- [ ] List/new/detail, approve (one-way), delete (Admin-only, blocked once approved), duplicate-account-per-budget validation
- [ ] Variance report tab, lazy-loaded/cached, all-time actuals (§4.14)

**Reports**
- [ ] Dashboard (KPIs, AP/AR outstanding with the PARTIAL no-op filter, recent entries, no charts)
- [ ] Trial Balance (date range, netted debit/credit columns + grand totals, grouped by account type)
- [ ] Income Statement (Revenue/COS/Expenses sections, gross profit, net surplus)
- [ ] Balance Sheet (as-of date, synthetic P&L rollup row, is_balanced banner)
- [ ] GL Detail (running balance, closing balance)
- [ ] Every report exportable to PDF and XLSX with the exact column sets in §8

**Shared/Global**
- [ ] All 5 smart-select widgets (Account/Bank/Vendor/Customer/Item) with typeahead, pinned quick-create row, inline create dialogs per §7.1, nested account-select inside the bank-account create dialog
- [ ] 25-row client-side pagination everywhere, resetting on filter/tab change
- [ ] All three status-color systems reproduced per-screen exactly as cataloged in §7.3
- [ ] Design tokens and bundled fonts applied throughout
- [ ] App packaged as a single Windows `.exe` with no external runtime dependencies

Nothing on this checklist may be marked done without being exercised in the running app at least once.
