# PRD — "Page Desktop" — Standalone Windows + Mac Accounting App (Electron + Node/TypeScript + SQLite)

**Status:** Approved for build
**Supersedes:** `docs/flet-desktop-port/PRD.md` (Python + Flet approach, 2026-07-15). That approach required rebuilding every screen from a prose spec in an unfamiliar UI framework. This approach reuses the existing, already-built Angular frontend directly and only reimplements the backend.
**Source of truth for behavior:** the live Page web system (Django + Neo4j backend, Angular 17 frontend) in this repository, as of 2026-07-16 — including the company_id multi-tenancy refactor (`Company`/`Membership`, per-company JWT claims, switch/join/create-company flows, `85bf7d2`/`8278119`/`c58287e`), vendor/customer statements (`a6cddfe`/`28da4fb`), and the `items` cost/selling-price split (`dcf9f1e`/`e9549d9`), all shipped after this PRD's first draft. See §3a, §5.1a, and §10 quirk 12 for the parts of the multi-tenancy refactor that most affect this port.

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
| Auth | Real JWT (access + refresh), issued by the local Express server, embedding `username`, and — once a company is resolved — `company_id`/`company_name`/`role` in the payload — mirrors `config/urls.py`'s `SageTokenObtainPairSerializer` + `switch_company` exactly (§5.1, §5.1a) | The existing Angular `auth.service.ts` already decodes a JWT and derives `roles: [payload.role]` from that single `role` claim; reproducing the same token shape means **zero frontend auth code changes**. There is still no real network exposure (server only binds to `localhost`), but reusing JWT is simpler than redesigning the auth flow, unlike the Flet plan which had to invent an in-memory session model from scratch. |
| Multi-tenancy | **`companies`/`memberships` tables in SQLite** (mirrors `users/models.py`'s Django ORM `Company`/`Membership` — an auth-side concept, not a Neo4j/graph one) | The live system was refactored mid-project to support multiple companies per install (§5.1a); the reused Angular frontend already ships a company-switcher screen and admin/members screen that expect this. Whether a single-machine desktop install actually needs multi-company support is an open question (see §5.1a), but if built, the schema and endpoints must match exactly. |
| XLSX export | **exceljs** | Pure JS/TS, no native dependency, same bolded-header-row output shape as the existing `openpyxl` exports. |
| PDF export | **pdfmake** (preferred) or **pdf-lib** as fallback | Pure JS/TS, no native binary dependencies, no headless-Chromium-inside-Electron weirdness (rules out Puppeteer). |
| Packaging | **electron-builder** → NSIS installer (Windows `.exe`) and `.dmg` (Mac) | One config produces both targets; handles native-module (`better-sqlite3`) rebuilding per target platform as a standard, well-documented step. |
| Currency | Nigerian Naira, symbol `₦`, always 2 decimals, thousands separator — **already implemented** in the Angular app's `number:'1.2-2'` pipe usage; the backend only needs to return raw numeric values, not pre-formatted strings, exactly as the current Django API does. | |
| Date/time | Local system clock only — no timezone conversion logic, same deliberate simplification as the Flet PRD (§ "Date/time" row there): a single-machine offline app has no cross-timezone concern. | |

---

## 3. Data Model

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §3** — every table, column, type, constraint, and relationship translation is identical, **except for the two deltas in §3a/§3b below, both shipped in the live system after that PRD's data model was written.** Only the implementation target changes: instead of SQLAlchemy declarative models, express the same schema as Kysely-typed table interfaces plus migration SQL (`CREATE TABLE` statements with the same columns/constraints/foreign keys/checks).

Read `docs/flet-desktop-port/PRD.md` §3.1–3.7 in full before writing any migration. In summary, the tables are:

- **Auth/RBAC**: `users`, `groups`, `user_groups`, `invite_codes`, **`companies`, `memberships`** (new — see §3a)
- **Accounts**: `accounts` (self-referential `parent_id` tree)
- **Journals**: `fiscal_years`, `accounting_periods`, `journal_entries`, `journal_lines`
- **Banks**: `bank_accounts`, `bank_reconciliations`, `reconciliation_lines` (join table replacing the `RECONCILES` relationship), `bank_transactions`, `bank_txn_counters`, `invoice_settlement_counters`
- **Payables**: `vendors`, `purchase_invoices`, `purchase_invoice_lines`, `items` (see §3b for a price-column change), `ap_payments`
- **Receivables**: `customers`, `sales_invoices`, `sales_invoice_lines`, `ar_receipts`
- **Budget**: `budgets`, `budget_lines`

All primary keys are `TEXT` UUID strings (mirrors `UniqueIdProperty` from neomodel), generated the same way (`crypto.randomUUID()` in Node instead of Python's `uuid4()`).

### 3a. Multi-tenancy: `company_id` on every domain table, plus `companies`/`memberships`

Shipped after the Flet PRD's data model was written (`85bf7d2`, `8278119`): every domain table listed above under Accounts/Journals/Banks/Payables/Receivables/Budget — i.e. every table backed by a Neo4j `StructuredNode` in the live system — gains a **required, indexed `company_id TEXT NOT NULL`** column, and every query against it must be scoped to the active company (§4.17). The exact set of tables needing this column, taken directly from `backend/users/management/commands/backfill_company_id.py`'s `DOMAIN_LABELS`: `accounts`, `bank_accounts`, `bank_reconciliations`, `bank_transactions`, `fiscal_years`, `accounting_periods`, `journal_entries`, `journal_lines`, `vendors`, `purchase_invoices`, `purchase_invoice_lines`, `items`, `ap_payments`, `customers`, `sales_invoices`, `sales_invoice_lines`, `ar_receipts`, `budgets`, `budget_lines`.

Two new SQLite/auth tables (Django ORM in the live system's `users/models.py` — these belong with `users`/`invite_codes`, not with the Neo4j-derived domain tables above):
- **`companies`**: `id` (UUID PK), `name`, `created_at`.
- **`memberships`**: `id`, `user_id` (FK → `users`), `company_id` (FK → `companies`), `role` (`Admin`/`Manager`/`Accountant`/`Staff`), `created_at`; unique on `(user_id, company_id)`.
- `invite_codes` gains `company_id` (nullable FK — legacy codes predating this refactor have none) and `role` (the role a redeemed code grants).

Whether a single-machine desktop install genuinely needs multi-company support at all is an open question worth raising with the user before building it (see §5.1a) — but if built, this column and these two tables must exist and be enforced exactly, because the reused Angular frontend's `AuthService`, company-select screen, and admin/members screen all expect the real API shape regardless of whether a given install ever has more than one company.

### 3b. `items`: `unit_price` split into `cost_price` + `selling_price`

Shipped in `dcf9f1e`/`e9549d9`, after the Flet PRD's `items` table spec was written. The `items` table now has **`cost_price REAL NOT NULL DEFAULT 0`** and **`selling_price REAL NOT NULL DEFAULT 0`** instead of a single `unit_price` column. `purchase_invoice_lines.unit_price` is unaffected — items remain UI-template-only (per `CLAUDE.md`'s "Item autofill pattern"), so this is purely an `items`-table change, not an invoice-line change.

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

**New since the Flet PRD (not covered there — implement from the live-system references below directly, not from `docs/flet-desktop-port/PRD.md`):**

- **§4.17 Company-scoped data visibility** (cross-cutting, applies to every rule above): every read/write on every domain table (§3a's list) filters by `company_id = <active company>`. "Active company" is the `company_id` claim on the validated JWT (`backend/config/auth.py`'s `get_active_company_id()`) — a token issued before the user resolved to a single company (0 or >1 memberships at login time) carries no `company_id` claim. Reproduce whatever the specific live endpoint actually does in that case rather than standardizing on one behavior — e.g. the invite-codes/members endpoints return `400 {"detail": "No active company..."}`, while most domain-data endpoints simply return empty results because nothing matches a null `company_id`.
- **§4.18 Vendor/customer statement** (`backend/payables/services.py::get_vendor_statement`, `backend/receivables/services.py::get_customer_statement`): pulls every POSTED/PAID invoice for the vendor/customer plus every payment/receipt against each into one event list; sorts by `(date, invoice-before-same-day-settlement)`; walks it computing a running balance — vendor: `+= credit - debit` (invoices increase what's owed, payments decrease it); customer: the mirror, `+= debit - credit`. Available as JSON, PDF, and XLSX (§8).
- **§4.19 Outstanding balance on vendor/customer lists**: the vendor and customer list endpoints add a per-row outstanding-balance figure computed as `max(0, total_amount - amount_paid)` (vendors) / `max(0, total_amount - amount_received)` (customers), summed only over that vendor's/customer's own POSTED/PAID invoices — a domain-relationship read, not a GL account query. Do not implement it as a GL query.

Do not "improve" any of these rules. Every threshold (₦0.01 tolerances used in the overpay guard, fully-paid detection, reconciliation completion, and balance-sheet balance check) must be copy-paste exact.

---

## 5. Auth & RBAC Spec

Real JWT, issued locally — **not** the Flet PRD's in-memory-session redesign, because the existing Angular `auth.service.ts` already expects and decodes a JWT.

### 5.1 Local session model
On app launch, the Electron `BrowserWindow` loads `http://localhost:8002/`, which serves the Angular app's login screen (Angular's own routing handles this — no change needed). On successful login, the local Express server issues an access + refresh JWT pair with the same claims as `config/urls.py`'s `SageTokenObtainPairSerializer` (`username`, plus `company_id`/`company_name`/`role` once a company is resolved — §5.1a). Angular stores them under the existing `page_access`/`page_refresh` `localStorage` keys — unchanged. Token lifetimes can stay the same as the original (8h access / 7d refresh, auto-rotation) purely for behavioral parity, even though the local-only network surface makes the security rationale moot; do not remove the refresh flow, since the Angular `AuthService` already calls it and removing it would require a frontend change.

### 5.1a Multi-tenancy: Company/Membership (shipped `85bf7d2`/`c58287e`, after this section was first drafted)
The live system now supports multiple companies per install, each user holding a `Membership` (with a `role`) in one or more `Company` records. Reproduce this exactly — the reused Angular frontend already ships the company-switcher and admin/members screens that depend on it, and `auth.service.ts` already has the corresponding methods (`switchCompany`, `getMemberships`, `joinCompany`, `createCompanyForCurrentUser`, `registerCompany`) waiting for a backend to answer them. **Worth flagging to the user before building**: a single-machine, single-install desktop app arguably never needs more than one company — but "total feature parity" (§1) means matching the real API shape either way, since the UI already expects it.

- **Login-time company resolution**: if a user has exactly one `Membership`, the login response's JWT embeds that membership's `company_id`/`company_name`/`role` directly (`_embed_company_claims` in `config/urls.py`) — transparent for the common case. A user with 0 or >1 memberships gets a **pre-company token** (no `company_id` claim); Angular routes them to the company-select screen, which calls `POST /api/auth/switch-company/` to obtain a fresh token pair carrying the chosen company's claims. Every company-scoped endpoint must reject/degrade a pre-company token per §4.17.
- **Four distinct account/company creation entry points** — do not collapse these into one flow; the Angular signup screen exposes them as genuinely different modes:
  - `POST /api/auth/register/` — join an **existing** company via invite code, creating a **new** `User` (the original registration flow, now company-aware: also creates a `Membership` with the invite code's `role`).
  - `POST /api/auth/register-company/` — create a **brand-new company** and a **brand-new** `User` who becomes that company's `Admin`. No invite code involved.
  - `POST /api/auth/join-company/` — add a `Membership` to the **current, already-logged-in** user via an invite code (never creates a `User`).
  - `POST /api/auth/create-company/` — create a brand-new company for the **current, already-logged-in** user, who becomes its `Admin` (never creates a `User`).
- **`POST /api/auth/switch-company/`**: body `{ company_id }`; `403` if the caller has no `Membership` in that company; otherwise issues a fresh token pair with that membership's claims.
- **`GET /api/auth/me/`** additionally returns `active_company_id` and `memberships: [{ company_id, company_name, role }]` (drives the company-select screen's choice list).
- **`GET /api/users/members/`** (list active company's members) and **`PATCH /api/users/members/{id}/`** (change a member's role) — Admin-only (§5.3); refuses (`400`) to demote a company's last remaining `Admin` rather than silently allowing a company with zero Admins.

### 5.2 Registration flow
Field-validation rules reproduced exactly per `docs/flet-desktop-port/PRD.md` §5.2: single-use, 7-day TTL invite code, `username`/`password` (≥8 chars)/`confirm_password` match, unique username/email, no auto-login after signup. **One detail has changed since that section was written**: redemption no longer get-or-creates a `Staff` Django group assignment — it creates a `Membership` in the invite code's linked company with the **role the invite code was generated for** (`Admin`/`Manager`/`Accountant`/`Staff`, not always `Staff`); see §5.1a for the other three account/company-creation entry points that share these same field-validation rules.

### 5.3 Permission matrix
Reproduced exactly per `docs/flet-desktop-port/PRD.md` §5.3 for the *action list itself* (Account create/edit/delete, Fiscal Year creation, Budget deletion, Invite Code management), everything else requires only being logged in. Do not tighten or loosen this list in the new backend.

**But the mechanism behind that list is now split in two, and both halves must be reproduced exactly as-is — see §10 quirk 12:**
- Invite-code management (`/api/users/invite-codes/`) and the newer team-member management (`/api/users/members/`, §5.1a) are gated by the **company-scoped role** — `is_admin(request)` in `backend/config/auth.py`, reading the JWT's `role` claim — and were **tightened to Admin-only**, no longer Admin-or-Manager.
- Every other role gate in the live system (Account CRUD, Fiscal Year creation, Budget deletion/approval, Journal Entry post/void, Bank Account/Reconciliation create/complete) still checks the **legacy, global Django `Group` membership** (`request.user.groups.filter(name__in=['Manager', 'Admin'])`), a system the company refactor never wired up against the new `Membership.role`.

### 5.4 UI-level gating quirk (interacts with the §5.3 split)
This lives entirely in the **existing Angular code** already and requires no backend change — the frontend's RBAC getters (`canManage`, `canDelete`, per `CLAUDE.md`) are reused as-is, and now derive `roles` from the JWT's single `role` claim (§5.1a), not Django groups. The backend must still enforce the real permission matrix (§5.3) server-side regardless of what the UI shows/hides — and because of the §5.3 split, for most actions the check that actually fires is against **legacy Django groups**, which can disagree with the company `role` the UI used to decide whether to show the button in the first place (e.g. a user who is `Admin` of their company but was never added to the Django `Admin` group sees a Post/Void button the backend then 403s). Reproduce this disagreement; do not "fix" it by pointing the backend check at the company role instead.

---

## 6. Frontend — reused, not rebuilt

The Angular app under `frontend/sage-frontend/src/app/**` is the **literal UI source of truth**. Do not rebuild, respec, or reinterpret any screen — build the Electron app's `ng build` output into the app bundle and serve it from the local Express server (§2).

**Minimal changes to the Angular codebase** (verify these are the *only* changes needed — do not go looking for more):
1. None expected to `api-base.ts` — it already derives `API_ROOT` from `window.location.protocol`/`window.location.hostname` (changed in `c58287e`, after this PRD's first draft, to make the live app reachable from any machine on the network) rather than a hardcoded host. Since the Electron app serves both frontend and API from the same `localhost:8002` origin, this already resolves correctly with zero further change — confirm empirically during Phase 3 of the build (§ below), but there is no longer any open question about *whether* a change is needed here.
2. If a build-time flag ends up being needed to distinguish "desktop build" from "web build" (e.g. for a future feature), add it as a minimal Angular environment file — but do not add one speculatively; only if a real need surfaces during the build.
3. No changes needed to `auth.service.ts`, any `*.service.ts` files, any component, or any shared widget (`AccountSelectComponent`, `BankSelectComponent`, etc.) — the backend must conform to what these already expect, not the other way around. This now includes two entire screens added after this PRD's first draft that the backend must also serve: `auth/company-select` (shown when login resolves to 0 or >1 memberships, §5.1a) and `admin/members` (Admin-only team-member management, §5.1a) — both already built, neither needs frontend changes.

Everything the Flet PRD's §6 (screen-by-screen) and §7 (shared components/design tokens) had to specify from scratch is already implemented correctly in this Angular code. If you need to know exactly what a screen does, field-by-field, **read the actual `.component.ts`/`.html` file**, not a prose description.

---

## 7. Backend API Contract — the real spec

Unlike the Flet port, this backend has an executable specification: **the Angular service files under `frontend/sage-frontend/src/app/services/*.ts`** define every request the app will ever make, and the corresponding **`backend/*/serializers.py` and `backend/*/views.py`** define every response shape the app expects back (via each app's `_serialize_*(node)` helper pattern, per `CLAUDE.md`).

For every endpoint:
1. Read the Angular service method that calls it (path, method, request body shape).
2. Read the matching Django `serializers.py` + `views.py` (response JSON shape, status codes, error format).
3. Implement the Express route to match both exactly — same URL path (see the URL table in `CLAUDE.md`), same field names, same status codes, same error shape (`{ detail: "..." }`, matching the Angular error-handling convention `e.response?.data?.detail`).

This is a stronger, more checkable spec than prose because it's the literal, already-working contract — cross-check against real files, not against a description of them.

Full URL surface to reimplement (from `CLAUDE.md`, plus the multi-tenancy/statement/export endpoints added after `CLAUDE.md`'s URL table was last written — see §3a, §4.18, §5.1a):
```
/api/auth/token/            /api/auth/token/refresh/    /api/auth/me/    /api/auth/register/
/api/auth/switch-company/   /api/auth/register-company/ /api/auth/join-company/  /api/auth/create-company/
/api/accounts/
/api/banks/accounts/        /api/banks/transactions/     /api/banks/transactions/import/
/api/banks/transactions/export/   /api/banks/reconciliations/
/api/journals/entries/      /api/journals/fiscal-years/  /api/journals/periods/
/api/payables/vendors/      /api/payables/vendors/{id}/statement/
/api/payables/invoices/     /api/payables/items/         /api/payables/items/export/
/api/receivables/customers/ /api/receivables/customers/{id}/statement/
/api/receivables/invoices/
/api/budget/budgets/        /api/budget/budgets/{id}/variance/
/api/users/invite-codes/    /api/users/members/          /api/users/members/{id}/
/api/reports/trial-balance/ /api/reports/income-statement/ /api/reports/balance-sheet/
/api/reports/gl-detail/     /api/reports/dashboard/
```
All report endpoints, plus the vendor/customer statement and items-export endpoints above, accept `?format=pdf|xlsx` exactly as today.

---

## 8. Export/Print Column Reference

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §8** — used as the column spec for the new `exceljs`/`pdfmake` export code, not as a UI spec (the on-screen tables already exist in Angular). See that section for the full table.

**New exports since that section was written (not in the Flet PRD — column sets below, taken directly from the live code, §4.18/§4.19):**
- **Items export** (`/api/payables/items/export/`): `Name, Type, Vendor, Cost Price (₦), Selling Price (₦)`.
- **Vendor statement** / **Customer statement** (`/api/payables/vendors/{id}/statement/`, `/api/receivables/customers/{id}/statement/`): `Date, Type (INVOICE/PAYMENT or INVOICE/RECEIPT), Reference, Description, Debit, Credit, Running Balance`.

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

**New quirk since the above 11 were written (§5.3/§5.4 have the full explanation) — this one is not carried forward from the Flet PRD, it's from the live company_id refactor:**

12. Two parallel, disconnected RBAC systems now coexist. Invite-code and team-member management check the new company-scoped `Membership.role` (via the JWT's `role` claim) and are Admin-only. Every other role-gated action in the system (Account CRUD, Fiscal Year creation, Budget deletion/approval, Journal Entry post/void, Bank Account/Reconciliation create/complete) still checks legacy, global Django `Group` membership, which the company refactor never wired up against `Membership.role` — so a user who is their company's `Admin` but was never separately added to the Django `Admin`/`Manager` group will have those actions rejected even though the UI, driven by the same JWT `role` claim, shows the button as available. Do not unify these two systems; reproduce the disagreement exactly.

---

## 11. Out of Scope (v1)

**Carried forward unchanged from `docs/flet-desktop-port/PRD.md` §11**: no network sync between installs or with the live system, no email sending, no real payment gateway integration, no exam-specific tooling, no multi-user concurrency/cloud backup, no changes to the existing live Django/Angular/Neo4j system, no formal automated test suite requirements beyond what the build prompt specifies for its own verification.

---

## 12. Feature Parity Checklist (acceptance criteria)

Reframed from the Flet PRD's screen-by-screen checklist: since the UI already exists and works, every item here is a **backend contract match**, not a UI build. "Done" means: the local Express endpoint(s) that a given Angular service method calls return the same shape and produce the same side effects as the current Django endpoint, verified by using the actual reused Angular screen against the local backend.

**Foundation**
- [ ] Electron app launches, creates its SQLite file in `userData` on first run, runs migrations, starts the local Express server, and loads the Angular app
- [ ] `Admin`/`Manager`/`Accountant` groups seeded on first run; `Staff` created lazily on first registration
- [ ] Decide-and-document: does this desktop install need real multi-company support, or can it special-case exactly one `Company` at first launch? (§3a/§5.1a — raise with the user if unresolved; either way, the API shape below must match)
- [ ] Every domain table carries `company_id` and every domain query is scoped by the active company (§3a, §4.17) — this underlies every checklist item below, not just this section

**Auth & Users** (`auth.service.ts`, `users.service.ts`)
- [ ] `/api/auth/token/`, `/api/auth/token/refresh/`, `/api/auth/me/`, `/api/auth/register/` match the existing JWT contract exactly, **including** `company_id`/`company_name`/`role` claims once a company resolves (§5.1a) — verified by logging in through the actual reused Login screen
- [ ] `/api/auth/switch-company/`, `/api/auth/register-company/`, `/api/auth/join-company/`, `/api/auth/create-company/` (§5.1a) — verified through the actual reused company-select and signup screens
- [ ] Invite Codes endpoints (`/api/users/invite-codes/`) and Members endpoints (`/api/users/members/`, `/api/users/members/{id}/`) — both Admin-only per the tightened company-role check (§5.3), verified through the actual Admin and admin/members screens
- [ ] The §10 quirk-12 RBAC split (legacy Django groups vs. company role) reproduced, not unified

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
- [ ] Vendors, Items CRUD — Items with `cost_price`/`selling_price` (§3b), not a single `unit_price`
- [ ] AP Invoice lifecycle (§4.9): create/edit, post, void, record payment incl. partial payments and atomic settlement reference, item-autofill contract preserved (frontend-only, verify backend doesn't break it)
- [ ] Vendor statement (§4.18) as JSON/PDF/XLSX, verified through the actual reused vendor statement screen
- [ ] Outstanding balance ("Amount Owed") on the vendor list (§4.19)
- [ ] Items export to PDF/XLSX (§8), verified through the actual reused Items screen

**Receivables** (`receivables.service.ts`)
- [ ] Full mirror of Payables (§4.10), including the customer statement (§4.18) and outstanding-balance column (§4.19)

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
