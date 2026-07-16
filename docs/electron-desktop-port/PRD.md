# PRD — "Page Desktop" — Standalone Windows + Mac Accounting App (Electron + Node/TypeScript + SQLite)

**Status:** Approved for build
**Supersedes:** `docs/flet-desktop-port/PRD.md` (Python + Flet approach, 2026-07-15). That approach required rebuilding every screen from a prose spec in an unfamiliar UI framework. This approach reuses the existing, already-built Angular frontend directly and only reimplements the backend.
**Source of truth for behavior:** the live Page web system (Django + Neo4j backend, Angular 17 frontend) in this repository, as of 2026-07-15.

---

## 1. Overview & Goals

**What this is:** a single-installer desktop application, built with **Electron**, that runs the **existing Angular frontend essentially unmodified** against a **new local Node/TypeScript backend** backed by **SQLite**, instead of the networked Django + Neo4j backend. Fully offline, no network calls, one embedded DB file per install.

**Why Electron, and why this reuses more than the Flet plan did:** the Angular frontend already talks to a REST API over HTTP with JWT auth stored in `localStorage` (see `frontend/sage-frontend/src/app/services/api-base.ts`, `auth.service.ts`) — exactly the shape Electron is built to wrap. Electron loads a Chromium window pointed at a local server; it does not require re-implementing any UI. Only the backend (currently Django + neomodel/Neo4j) needs a new implementation, because the database is changing to SQLite and Neo4j's graph model (`neomodel.StructuredNode`, Cypher queries) has no SQLite equivalent.

**Why it exists:**
- **Primary use, real accounting work**: lets Topfaith University run the same double-entry accounting workflows (chart of accounts, journal entries, bank reconciliation, AP/AR, budgets, financial reports) on a machine with no network access.
- **Secondary use, teaching/testing sandbox**: the same binary is handed to accounting students on lab/exam PCs so they can practice the full workflow hands-on. There is no special exam mode — students use the identical app an accountant would use. Any proctoring, data collection, or grading process happens outside the app (out of scope, see §11).

**Relationship to the existing system:** independent artifact. It does not talk to the live Django API, does not require Neo4j, and does not sync with the web app's database. The **frontend code is shared/reused**; the **backend is a from-scratch reimplementation of the same API contract**.

**Guiding constraint — total feature parity:** every endpoint, computed value, validation rule, and even the *known quirks* of the current system (§10) must be reproduced by the new backend. The existing Angular app is the literal UI source of truth and must not be modified beyond the minimal changes noted in §6.

---

## 2. Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| App shell | **Electron** | Wraps a Chromium window around a local web app; native installers for both Windows and Mac from one codebase via `electron-builder`. No UI to rebuild — see §6. |
| Frontend | **The existing Angular app** (`frontend/sage-frontend`), built via its existing `ng build`, copied into the Electron bundle and served as static assets | Reused, not rewritten. All ~30 screens, shared "smart select" widgets, pagination, design tokens, and business-rule-driven form behavior already exist and are already correct against the live system. |
| Backend | **Node.js + TypeScript + Express**, started by Electron's main process on `localhost:8002`, serving both `/api/*` and the built Angular static assets from one origin | Same origin for API and frontend means `api-base.ts`'s existing `window.location.hostname`-based URL derivation keeps working **unchanged** — no frontend source change needed for API routing. Express mirrors DRF's role closely enough that the existing Django `urls.py`/`viewsets.py` structure (§ tables below) can be translated route-by-route. |
| Local storage | **SQLite**, accessed via **better-sqlite3** (synchronous native driver) + **Kysely** (type-safe SQL query builder on top) | `better-sqlite3` is the standard Electron+SQLite combination — well-documented native-module rebuild path via `electron-builder`/`@electron/rebuild`, unlike Prisma, whose per-platform native query-engine binaries are a known Electron packaging pain point. Kysely gives typed queries/joins without an ORM's magic, keeping ~20 tables' worth of hand-written SQL from becoming a correctness liability (same rationale the Flet PRD used to justify SQLAlchemy over raw `sqlite3`). |
| Schema management | Kysely migration files define schema; migrations run automatically on first launch (and on version upgrades) against the SQLite file in `app.getPath('userData')`. No fleet-wide upgrade-in-place requirement for v1 — fresh installs only. |
| Password hashing | Node's stdlib `crypto.scrypt` (no native compiled dependency beyond what's already required for `better-sqlite3`) | Salted scrypt is adequate for a local single-user-at-a-time desktop app; avoids adding another native dependency (e.g. `bcrypt`) to the packaging surface. |
| Auth | Real JWT (access + refresh), issued by the local Express server, embedding `username` + `groups` in the payload — mirrors `config/urls.py`'s `SageTokenObtainPairSerializer` exactly | The existing Angular `auth.service.ts` already decodes a JWT and reads roles from it; reproducing the same token shape means **zero frontend auth code changes**. There is still no real network exposure (server only binds to `localhost`), but reusing JWT is simpler than redesigning the auth flow, unlike the Flet plan which had to invent an in-memory session model from scratch. |
| XLSX export | **exceljs** | Pure JS/TS, no native dependency, same bolded-header-row output shape as the existing `openpyxl` exports. |
| PDF export | **pdfmake** (preferred) or **pdf-lib** as fallback | Pure JS/TS, no native binary dependencies, no headless-Chromium-inside-Electron weirdness (rules out Puppeteer). |
| Packaging | **electron-builder** → NSIS installer (Windows `.exe`) and `.dmg` (Mac) | One config produces both targets; handles native-module (`better-sqlite3`) rebuilding per target platform as a standard, well-documented step. |
| Currency | Nigerian Naira, symbol `₦`, always 2 decimals, thousands separator — **already implemented** in the Angular app's `number:'1.2-2'` pipe usage; the backend only needs to return raw numeric values, not pre-formatted strings, exactly as the current Django API does. | |
| Date/time | Local system clock only — no timezone conversion logic, same deliberate simplification as the Flet PRD (§ "Date/time" row there): a single-machine offline app has no cross-timezone concern. | |

---

## 3. Data Model

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §3** — every table, column, type, constraint, and relationship translation is identical. Only the implementation target changes: instead of SQLAlchemy declarative models, express the same schema as Kysely-typed table interfaces plus migration SQL (`CREATE TABLE` statements with the same columns/constraints/foreign keys/checks).

Read `docs/flet-desktop-port/PRD.md` §3.1–3.7 in full before writing any migration. In summary, the tables are:

- **Auth/RBAC**: `users`, `groups`, `user_groups`, `invite_codes`
- **Accounts**: `accounts` (self-referential `parent_id` tree)
- **Journals**: `fiscal_years`, `accounting_periods`, `journal_entries`, `journal_lines`
- **Banks**: `bank_accounts`, `bank_reconciliations`, `reconciliation_lines` (join table replacing the `RECONCILES` relationship), `bank_transactions`, `bank_txn_counters`, `invoice_settlement_counters`
- **Payables**: `vendors`, `purchase_invoices`, `purchase_invoice_lines`, `items`, `ap_payments`
- **Receivables**: `customers`, `sales_invoices`, `sales_invoice_lines`, `ar_receipts`
- **Budget**: `budgets`, `budget_lines`

All primary keys are `TEXT` UUID strings (mirrors `UniqueIdProperty` from neomodel), generated the same way (`crypto.randomUUID()` in Node instead of Python's `uuid4()`).

---

## 4. Business Logic Spec

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §4** — every rule, threshold, rounding behavior, and ordering of checks is identical; reproduce it in TypeScript instead of Python. This is the load-bearing correctness core of the app. Read `docs/flet-desktop-port/PRD.md` §4.1–4.16 in full before implementing any endpoint. In summary:

- §4.1 Account code auto-generation (non-atomic scan-then-insert, write-once `code`/`opening_balance`)
- §4.2 Journal entry reference auto-generation (non-atomic, today's-date-based)
- §4.3 Manual journal entry validation & balance rule (checked twice: create/update and post)
- §4.4 Posting and voiding a journal entry (no role gate at the business-logic layer — see §5)
- §4.5 Account balance computation (always derived, never a stored running total)
- §4.6 Opening balance auto-posting (idempotent, keyed by `OB-{account_id}`)
- §4.7 Bank transaction creation (shared path for manual entry, CSV import, and AP/AR auto-generated transactions)
- §4.8 Atomic reference counters (bank transaction refs, invoice settlement refs — implemented as a SQLite transaction with `INSERT ... ON CONFLICT DO UPDATE`, the direct Kysely/SQLite equivalent of the original's Cypher `MERGE` counter pattern)
- §4.9 AP invoice lifecycle (post, void, record payment incl. partial payments and the ₦0.01 overpay-guard slack)
- §4.10 AR invoice lifecycle (mirror of §4.9)
- §4.11 `AccountType` enum and normal-balance rule (10 values, exact debit/credit-normal split)
- §4.12 Bank reconciliation (toggle line, get GL lines, complete with ₦0.01 tolerance, one-way)
- §4.13 CSV bank statement import (exact column/date-format/error rules)
- §4.14 Budget lifecycle & variance (all-time actuals, no date filtering)
- §4.15 Financial reports (trial balance netting, income statement, balance sheet incl. synthetic P&L rollup row, GL detail running balance, dashboard)
- §4.16 Export/print mechanics (column sets — see §8 below)

Do not "improve" any of these rules. Every threshold (₦0.01 tolerances used in the overpay guard, fully-paid detection, reconciliation completion, and balance-sheet balance check) must be copy-paste exact.

---

## 5. Auth & RBAC Spec

Real JWT, issued locally — **not** the Flet PRD's in-memory-session redesign, because the existing Angular `auth.service.ts` already expects and decodes a JWT.

### 5.1 Local session model
On app launch, the Electron `BrowserWindow` loads `http://localhost:8002/`, which serves the Angular app's login screen (Angular's own routing handles this — no change needed). On successful login, the local Express server issues an access + refresh JWT pair with the same claims as `config/urls.py`'s `SageTokenObtainPairSerializer` (`username`, `groups`). Angular stores them under the existing `page_access`/`page_refresh` `localStorage` keys — unchanged. Token lifetimes can stay the same as the original (8h access / 7d refresh, auto-rotation) purely for behavioral parity, even though the local-only network surface makes the security rationale moot; do not remove the refresh flow, since the Angular `AuthService` already calls it and removing it would require a frontend change.

### 5.2 Registration flow
Reproduced exactly per `docs/flet-desktop-port/PRD.md` §5.2: invite-code-gated, single-use, 7-day TTL, `username`/`password` (≥8 chars) /`confirm_password` match, unique username/email, get-or-create `Staff` group assignment, no auto-login after signup.

### 5.3 Permission matrix
Reproduced exactly per `docs/flet-desktop-port/PRD.md` §5.3 — same narrow role-gated action list (Account create/edit/delete, Fiscal Year creation, Budget deletion, Invite Code management), everything else requires only being logged in. Do not tighten or loosen this in the new backend.

### 5.4 UI-level gating quirk
This lives entirely in the **existing Angular code** already and requires no backend change — the frontend's RBAC getters (`canManage`, `canDelete`, per `CLAUDE.md`) are reused as-is. The backend must still enforce the real permission matrix (§5.3) server-side regardless of what the UI shows/hides, exactly as the current Django backend does.

---

## 6. Frontend — reused, not rebuilt

The Angular app under `frontend/sage-frontend/src/app/**` is the **literal UI source of truth**. Do not rebuild, respec, or reinterpret any screen — build the Electron app's `ng build` output into the app bundle and serve it from the local Express server (§2).

**Minimal changes to the Angular codebase** (verify these are the *only* changes needed — do not go looking for more):
1. None expected to `api-base.ts` — since the Electron app serves both frontend and API from the same `localhost:8002` origin, `window.location.hostname` resolves to `localhost` automatically and `API_ROOT` already computes correctly. Confirm this in practice during Phase 3 of the build (§ below) before assuming any change is needed.
2. If a build-time flag ends up being needed to distinguish "desktop build" from "web build" (e.g. for a future feature), add it as a minimal Angular environment file — but do not add one speculatively; only if a real need surfaces during the build.
3. No changes needed to `auth.service.ts`, any `*.service.ts` files, any component, or any shared widget (`AccountSelectComponent`, `BankSelectComponent`, etc.) — the backend must conform to what these already expect, not the other way around.

Everything the Flet PRD's §6 (screen-by-screen) and §7 (shared components/design tokens) had to specify from scratch is already implemented correctly in this Angular code. If you need to know exactly what a screen does, field-by-field, **read the actual `.component.ts`/`.html` file**, not a prose description.

---

## 7. Backend API Contract — the real spec

Unlike the Flet port, this backend has an executable specification: **the Angular service files under `frontend/sage-frontend/src/app/services/*.ts`** define every request the app will ever make, and the corresponding **`backend/*/serializers.py` and `backend/*/views.py`** define every response shape the app expects back (via each app's `_serialize_*(node)` helper pattern, per `CLAUDE.md`).

For every endpoint:
1. Read the Angular service method that calls it (path, method, request body shape).
2. Read the matching Django `serializers.py` + `views.py` (response JSON shape, status codes, error format).
3. Implement the Express route to match both exactly — same URL path (see the URL table in `CLAUDE.md`), same field names, same status codes, same error shape (`{ detail: "..." }`, matching the Angular error-handling convention `e.response?.data?.detail`).

This is a stronger, more checkable spec than prose because it's the literal, already-working contract — cross-check against real files, not against a description of them.

Full URL surface to reimplement (from `CLAUDE.md`, unchanged):
```
/api/auth/token/            /api/auth/token/refresh/    /api/auth/me/    /api/auth/register/
/api/accounts/
/api/banks/accounts/        /api/banks/transactions/     /api/banks/transactions/import/
/api/banks/transactions/export/   /api/banks/reconciliations/
/api/journals/entries/      /api/journals/fiscal-years/  /api/journals/periods/
/api/payables/vendors/      /api/payables/invoices/      /api/payables/items/
/api/receivables/customers/ /api/receivables/invoices/
/api/budget/budgets/        /api/budget/budgets/{id}/variance/
/api/users/invite-codes/
/api/reports/trial-balance/ /api/reports/income-statement/ /api/reports/balance-sheet/
/api/reports/gl-detail/     /api/reports/dashboard/
```
All report endpoints accept `?format=pdf|xlsx` exactly as today.

---

## 8. Export/Print Column Reference

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §8** — used as the column spec for the new `exceljs`/`pdfmake` export code, not as a UI spec (the on-screen tables already exist in Angular). See that section for the full table.

---

## 9. Non-Functional Requirements

- **Fully offline**: no network calls anywhere in the running app.
- **Single SQLite file per install**: created on first launch if absent; no external DB service.
- **Currency formatting**: `₦#,##0.00` — already correct in the reused Angular templates; the backend just returns raw numbers.
- **Local time only**: no timezone conversion; the machine's wall clock is authoritative.
- **Packaging**: one Windows `.exe` (NSIS) **and** one Mac `.dmg`, via `electron-builder`, bundling Electron, the Node backend, the Angular `dist/` build, and a platform-specific rebuilt `better-sqlite3` binary — nothing downloaded at runtime.
- **Performance target**: smooth interaction at classroom-scale data volumes — hundreds to low thousands of accounts/entries/invoices per install, not enterprise-scale.
- **No multi-user concurrency handling required**: SQLite's default locking is sufficient since only one instance of the app runs against one DB file at a time on one machine.

---

## 10. "Replicate As-Is" Quirks List (do not silently fix)

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §10** — all 11 quirks apply regardless of wrapper choice, since they're properties of the business logic (§4), not the UI:

1. `JournalEntry.period`/`AccountingPeriod` linkage modeled but never populated; closing a period has no effect on posting.
2. Account codes, manual journal-entry references, and invoice numbers use non-atomic max-then-increment scans; bank-transaction references and invoice-settlement references use a genuinely atomic counter. Keep this asymmetry.
3. No role/group check at all on posting/voiding journal entries, posting/voiding/paying/receiving invoices, creating bank transactions, toggling/completing reconciliations, or approving budgets — only Account CRUD, Fiscal Year creation, Budget deletion, and Invite Code management are role-gated.
4. On 5 specific screens (already implemented in the reused Angular code), the button-visibility check that reads as a Manager/Admin check is actually "any logged-in user"; only the journal-entry form's Save & Post button does a real role check. (This is frontend behavior already present — the backend just needs to enforce the real matrix in §5.3 regardless of what the UI shows.)
5. The dashboard's AP/AR outstanding query filters invoice status by `IN ('POSTED','PARTIAL')` even though `'PARTIAL'` is never a valid status — permanently no-op, not a status to implement.
6. Voiding a journal entry or invoice never reverses/rewrites amounts — it only excludes the entry from POSTED-scoped queries going forward.
7. Bank Statement Import exists as both a standalone screen and an inline panel (already implemented in Angular), calling identical logic — the backend serves one shared import endpoint either way; nothing to change here.
8. Three separate, non-unified color systems for status display — already implemented in the reused Angular code; nothing for the backend to do.
9. Report table headers use a hardcoded near-black instead of the navy-primary token — already implemented in the reused Angular code.
10. Budgets have no edit screen or update path after creation — only create, approve, and (if still DRAFT) delete. The backend must not expose a budget update endpoint.
11. The journal-entry edit form's from/to row reconstruction (positional DEBIT/CREDIT pairing) is already implemented in the reused Angular code; the backend just needs to return lines in a stable, consistent order for it to work.

---

## 11. Out of Scope (v1)

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §11**: no network sync between installs or with the live system, no email sending, no real payment gateway integration, no exam-specific tooling, no multi-user concurrency/cloud backup, no changes to the existing live Django/Angular/Neo4j system, no formal automated test suite requirements beyond what the build prompt specifies for its own verification.

---

## 12. Feature Parity Checklist (acceptance criteria)

Reframed from the Flet PRD's screen-by-screen checklist: since the UI already exists and works, every item here is a **backend contract match**, not a UI build. "Done" means: the local Express endpoint(s) that a given Angular service method calls return the same shape and produce the same side effects as the current Django endpoint, verified by using the actual reused Angular screen against the local backend.

**Foundation**
- [ ] Electron app launches, creates its SQLite file in `userData` on first run, runs migrations, starts the local Express server, and loads the Angular app
- [ ] `Admin`/`Manager`/`Accountant` groups seeded on first run; `Staff` created lazily on first registration

**Auth & Users** (`auth.service.ts`, `users.service.ts`)
- [ ] `/api/auth/token/`, `/api/auth/token/refresh/`, `/api/auth/me/`, `/api/auth/register/` match the existing JWT contract exactly — verified by logging in through the actual reused Login screen
- [ ] Invite Codes endpoints (`/api/users/invite-codes/`) — generate/revoke/list, self-guarded to Admin/Manager, verified through the actual Admin screen

**Chart of Accounts** (`accounts.service.ts`)
- [ ] List/create/update/delete, code auto-generation (§4.1), code/opening-balance immutability, ledger + balance (§4.5), idempotent opening-balance posting (§4.6) — verified through the actual reused Chart of Accounts screens

**Journal Entries** (`journals.service.ts`)
- [ ] List with status filters, create/update (reference auto-gen §4.2, balance validation §4.3), post/void (§4.4) — verified through the actual reused Journal Entry screens

**Banking** (`banks.service.ts`, `bank-transactions.service.ts`)
- [ ] Bank Accounts CRUD, opening-balance immutability, GL linkage
- [ ] Bank transaction creation engine (§4.7) incl. all LEDGER/BANK/SUPPLIER/CUSTOMER routing, atomic reference counters (§4.8)
- [ ] CSV import (§4.13) exact parsing/skip/error rules, both import surfaces (standalone + inline)
- [ ] Bank Reconciliation: toggle/complete (§4.12), ₦0.01 tolerance
- [ ] CSV/XLSX export

**Payables** (`payables.service.ts`)
- [ ] Vendors, Items CRUD
- [ ] AP Invoice lifecycle (§4.9): create/edit, post, void, record payment incl. partial payments and atomic settlement reference, item-autofill contract preserved (frontend-only, verify backend doesn't break it)

**Receivables** (`receivables.service.ts`)
- [ ] Full mirror of Payables (§4.10)

**Budget** (`budget.service.ts`)
- [ ] List/create/approve/delete (no update endpoint — §10 item 10), variance computation (§4.14)

**Reports** (`reports.service.ts`)
- [ ] Dashboard, Trial Balance (netting rule), Income Statement, Balance Sheet (synthetic P&L rollup, `is_balanced`), GL Detail (running balance) — all matching §4.15 exactly
- [ ] Every report exportable to PDF and XLSX with the column sets in §8

**Packaging**
- [ ] `electron-builder` config produces a working Windows `.exe` (NSIS) and Mac `.dmg`
- [ ] `better-sqlite3` native module correctly rebuilt/bundled for both target platforms
- [ ] Clean install on both platforms boots the app and creates its SQLite file correctly on first run

Nothing on this checklist may be marked done without exercising it in the running Electron app (using the real, reused Angular UI) at least once.
