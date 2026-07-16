# Build Prompt — Page Desktop (Electron + Node/TypeScript + SQLite port)

Copy everything below this line into a fresh Claude Code or Codex session (with this repository open) to drive the build. It is self-contained — the agent does not need any other context from this conversation.

---

You are building a new, standalone desktop application called **"Page Desktop"**. It wraps the **existing Angular frontend** (`frontend/sage-frontend`) in **Electron**, backed by a new **Node.js/TypeScript/Express** local server and **SQLite** (via `better-sqlite3` + Kysely), replacing the existing Django + Neo4j backend. It must run fully offline, with zero network calls, and package into a Windows `.exe` and a Mac `.dmg`.

**The full functional specification is `docs/electron-desktop-port/PRD.md` in this repository. Read it in full before writing any code.** It references two other documents you must also read:
- `docs/flet-desktop-port/PRD.md` §3 (Data Model) and §4 (Business Logic Spec) — carried forward unchanged into the new PRD's §3/§4; these are the authoritative schema and business-rule specs, framework-agnostic.
- The actual Angular source under `frontend/sage-frontend/src/app/services/*.ts` and the actual Django source under `backend/*/serializers.py` + `backend/*/views.py` — these are the literal, executable API contract your new backend must match field-for-field (PRD §7). Do not rely on prose descriptions where the real files are available — read them directly.

**Do not modify anything under `backend/` or `frontend/sage-frontend/src/app/**` except the minimal, verified-necessary change described in PRD §6.** This is the core difference from the old Flet plan: the UI is reused, not rebuilt. If you find yourself writing new Angular components, screens, or business logic in the frontend, stop — that almost certainly means you've misunderstood the task. The only new code is: the Electron shell, the Node/Express backend, and the SQLite schema/migrations.

## Where to put the new app

Create the new app in a new top-level directory, e.g. `desktop/page_desktop/`, entirely separate from `backend/`. It should contain the Electron main/preload process code and the new Express backend. The Angular build output gets copied in as a build step, not hand-edited in place.

## Non-negotiable ground rules

1. **The PRD's feature-parity checklist (§12) is the literal definition of "done."** Every item must be verified by actually using the reused Angular screen against your local backend in the running Electron app (`electron .` in dev, or the packaged build) — not just "the code looks right."
2. **Reproduce the quirks in PRD §10 exactly.** Do not add role checks where none exist; do not "complete" the dead `PARTIAL` invoice status; do not make non-atomic reference counters atomic; do not give budgets an edit endpoint. If you think one of these is a bug worth fixing, say so in your final report — do not silently fix it.
3. **The Angular frontend is the UI spec. Read the actual component/service files, not a description of them**, whenever you're unsure what a screen does or what shape a request/response should be.
4. **Business logic and API-contract fidelity before packaging polish.** Get the SQLite schema, the auth/JWT layer, and the accounting engine (balance computation, journal posting, AP/AR posting/payment, bank transaction creation, reconciliation, reports) correct and verified against the real Angular screens before investing in packaging.
5. **Pure-JS/TS dependencies only** where possible (`exceljs`, `pdfmake`/`pdf-lib`, `crypto.scrypt`) — `better-sqlite3` is the one native dependency, and it's the standard, well-supported choice for Electron; do not substitute a heavier native stack (e.g. avoid bundling a headless browser for PDF generation).
6. **Currency, dates, and rounding must match the PRD exactly** — ₦ formatting is already handled by the reused Angular templates; your backend just needs to return correctly-rounded raw numbers. Get the recurring ₦0.01 tolerance (overpay guard, fully-paid detection, reconciliation completion, balance-sheet balance check) copy-paste exact from `docs/flet-desktop-port/PRD.md` §4.

## Build order

Work in these seven phases, in order. Each phase should end with the relevant PRD §12 checklist items verified working (against the real reused Angular UI) before moving to the next.

**Phase 1 — Foundation**
Electron shell (main process, preload script, `BrowserWindow`), Express server skeleton, SQLite schema via Kysely migrations for every table in PRD §3 (auth/RBAC tables first, then accounts, journals, banks, payables, receivables, budget). Main-process lifecycle: on `app.whenReady()`, create/open the SQLite DB in `app.getPath('userData')`, run migrations, start Express on `localhost:8002`, load `http://localhost:8002/` into the `BrowserWindow`, shut the server down cleanly on quit. Seed `Admin`/`Manager`/`Accountant` groups on first run (lazy-create `Staff` on first registration, not pre-seeded).

**Phase 2 — Auth**
`/api/auth/token/`, `/api/auth/token/refresh/`, `/api/auth/me/`, `/api/auth/register/`, matching the existing JWT payload shape (`username`, `groups`) exactly — read `config/urls.py`'s `SageTokenObtainPairSerializer` for the exact claim shape. Verify by logging into the actual reused Angular Login screen and confirming `AuthService`'s role-decoding logic works unmodified.

**Phase 3 — Wire in the existing Angular build**
Add a build step that runs `ng build` in `frontend/sage-frontend` and copies its `dist/sage-frontend` output into the Electron app's served static root; have Express serve it at `/`. Verify: launch the Electron app, confirm the Login screen renders, log in, confirm it lands on Chart of Accounts (per the existing routing behavior). Check whether `api-base.ts` needs any change now that frontend and API share an origin — PRD §6 expects it won't, but confirm this empirically before moving on, and if a change genuinely is needed, keep it as small as possible and document why.

**Phase 4 — Domain endpoints**
One Express router per app: accounts, journals (entries, fiscal-years, periods), banks (accounts, transactions, reconciliations), payables (vendors, invoices, items), receivables (customers, invoices), budget. For each endpoint, cross-reference the real Angular service method (`frontend/sage-frontend/src/app/services/*.ts`) and the real Django `serializers.py`/`views.py` `_serialize_*` helper output shape — match URL paths, field names, and status codes exactly (PRD §7's full URL list).

**Phase 5 — Business logic engine**
Implement PRD §4 (= `docs/flet-desktop-port/PRD.md` §4) in full: account code generation, journal reference generation, balance validation (checked at both create/update and post time), posting/voiding, account balance computation, idempotent opening-balance posting, the bank-transaction creation engine with its LEDGER/BANK/SUPPLIER/CUSTOMER routing, atomic reference counters (bank txn + invoice settlement — use a SQLite transaction with `INSERT ... ON CONFLICT DO UPDATE`), AP/AR invoice lifecycle incl. partial payments, CSV bank statement import (exact parsing/skip/error rules), budget lifecycle + variance, and all four reports + dashboard. This is the highest-risk phase — write it carefully and verify each rule against the actual reused Angular screens (e.g. post a journal entry through the real form, confirm the balance and status behave exactly as the live web system does).

**Phase 6 — Exports**
XLSX via `exceljs`, PDF via `pdfmake`/`pdf-lib`, matching the column sets in PRD §8. CSV export for bank transactions. Verify by triggering an export from the actual reused Angular export buttons and opening the resulting file.

**Phase 7 — Packaging**
`electron-builder` config producing a Windows NSIS `.exe` and a Mac `.dmg`. Ensure `better-sqlite3` is correctly rebuilt/bundled for each target platform (standard `electron-builder` native-module handling — do not hand-roll this). Verify a clean install on both platforms launches the app and creates its SQLite file correctly on first run.

## Verification expectations

Before declaring the build complete:
- Walk the entire PRD §12 checklist and mark each item, noting any that are incomplete or behave differently than specified.
- Manually exercise at least one full accounting cycle end-to-end in the running Electron app, using the real reused Angular screens: create accounts → post opening balances → create and post a manual journal entry → create a vendor, item, and AP invoice, post it, make a partial payment then a final payment → create a customer and AR invoice, post it, receive payment → create a bank account, record a transaction, run a reconciliation to completion → generate all four reports and confirm the balance sheet balances → export at least one report to PDF and one list to XLSX and confirm the files open correctly.
- Confirm the packaged `.exe` and `.dmg` each run on a machine/VM without any other software pre-installed.

## Final report

When you consider the build complete, report back with:
1. A completed/annotated copy of the PRD §12 checklist (done / not done / done-differently-because — with reasoning for any deviation).
2. Confirmation of exactly which (if any) Angular source files you touched, and why each change was necessary — this should be a very short list, ideally empty or just `api-base.ts`.
3. Any place you deliberately deviated from the PRD (should be none, but call it out explicitly if it happened and why).
4. Any of the PRD §10 quirks you found yourself tempted to "fix," and confirmation you left them as-is.
5. Instructions for building and running the packaged `.exe` and `.dmg`.
