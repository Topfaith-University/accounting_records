# Build Prompt — Page Desktop (Flet + SQLite port)

Copy everything below this line into a fresh Claude Code or Codex session (with this repository open) to drive the build. It is self-contained — the agent does not need any other context from this conversation.

---

You are building a new, standalone Python desktop application called **"Page Desktop"**. It is a from-scratch reimplementation of an existing Django + Neo4j + Angular accounting system, targeting Windows, built with **Flet** for the UI and **SQLite** (via SQLAlchemy) for local storage. It must run fully offline, with zero network calls, and package into a single Windows `.exe`.

**The full functional specification is `docs/flet-desktop-port/PRD.md` in this repository. Read it in full before writing any code.** It is the authoritative source for every data model field, every business rule, every screen's fields and behavior, every validation threshold, every color and font token, and — critically — a documented list of quirks in the original system (PRD §10) that must be **reproduced exactly, not fixed**. Do not rely on your own assumptions about "sensible" accounting-software behavior where the PRD specifies something different; the PRD reflects the actual behavior of a working, deployed system, verified field-by-field and screen-by-screen against its source code.

## Where to put the new app

Create the new app in a new top-level directory, e.g. `desktop/page_desktop/` in this repo, entirely separate from `backend/` and `frontend/`. Do not modify anything under `backend/` or `frontend/` — this is an independent artifact.

## Non-negotiable ground rules

1. **The PRD's feature-parity checklist (§12) is the literal definition of "done."** No phase below is complete until every relevant checklist item is implemented and you have personally exercised it in the running app (launch the app, click through the flow, observe correct behavior) — not just "the code looks right." If you cannot run a Windows `.exe` in your environment, run the Flet app in its normal Python/dev mode (`flet run` or equivalent) to exercise the UI; defer only the final `.exe` packaging step to a build script you write and document, not to unverified code.
2. **Reproduce the quirks in PRD §10 exactly.** In particular: do not add role checks where the PRD says none exist; do not "complete" the dead `PARTIAL` invoice status; do not unify the three status-color systems; do not make non-atomic reference counters atomic; do not give budgets an edit screen; do not consolidate the duplicated CSV-import UI into one screen. If you think one of these is a bug worth fixing, say so in your final report — do not silently fix it.
3. **Business logic before UI polish.** Get the SQLite schema, the auth/session layer, and the accounting engine (balance computation, journal posting, AP/AR posting/payment, bank transaction creation, reconciliation, reports) correct and tested before investing in pixel-level visual fidelity.
4. **No placeholder/stub screens.** Every screen listed in PRD §6 must be fully functional per its spec, not a "coming soon" placeholder.
5. **Pure-Python dependencies only** for exports (`openpyxl` for XLSX, `reportlab` or `fpdf2` for PDF) and password hashing (stdlib `hashlib.pbkdf2_hmac`) — no compiled/native dependencies that would complicate single-`.exe` packaging (this rules out WeasyPrint, bcrypt, etc. — see PRD §2 for the reasoning).
6. **Currency, dates, and rounding must match the PRD exactly** — ₦ formatting, 2-decimal rounding, the recurring ₦0.01 tolerance used in five different places (overpay guard, fully-paid detection, reconciliation completion, balance-sheet balance check — PRD §4 cross-references all of them). Get these thresholds copy-paste exact; they are not approximate.

## Build order

Work in these six phases, in order. Each phase should end with the relevant PRD §12 checklist items verified working before moving to the next.

**Phase 1 — Foundation**
SQLAlchemy models for every table in PRD §3 (auth/RBAC tables first, then accounts, journals, banks, payables, receivables, budget). `Base.metadata.create_all()` bootstrap on first launch. Local session/auth (PRD §5.1), login/signup/forgot-password screens (§6.1–6.3), the app shell with sidebar navigation (§6.4) including the Administration section's Admin/Manager gating. Seed the `Admin`, `Manager`, `Accountant` groups on first run (do not pre-seed `Staff` — create it lazily on first registration, exactly like the original).

**Phase 2 — Ledger core**
Chart of Accounts (§6.6–6.7) including auto code generation (§4.1) and the account-type/normal-balance dropdown+preview logic (§4.11). Journal Entries (§6.8–6.10) including the from/to row UI that expands into 2 lines per row, the reference generator (§4.2), the double-entry balance validation (§4.3) enforced at both save and post time, and posting/voiding (§4.4). The account balance engine (§4.5) and idempotent opening-balance posting (§4.6) — this is the load-bearing correctness core of the whole app; write it carefully and verify it with a few manual entries before moving on.

**Phase 3 — Banking**
Bank Accounts (§6.11–6.12), the generic bank-transaction creation engine (§4.7) and its atomic reference counter (§4.8), the Bank Transactions list with filters/export (§6.13), the multi-row transaction entry form with all four row types and their distinct routing rules (§6.14 — this is one of the most intricate screens in the spec, read it twice), both CSV import surfaces (§6.13's inline panel and §6.15's standalone screen) wired to the exact parsing/skip/error rules in §4.13, and the Bank Reconciliation screen (§6.16) with the toggle/complete logic in §4.12.

**Phase 4 — Reports**
All four report computations (§4.15) plus the Dashboard (§4.15's dashboard aggregate), their screens (§6.5, §6.28–6.31), and PDF/XLSX export for every exportable list/report using the exact column sets in PRD §8. Get the trial-balance netting rule and the balance-sheet's live synthetic P&L rollup exactly right — both are easy to get subtly wrong.

**Phase 5 — AP & AR**
Vendors, Items (§6.21–6.22), Purchase Invoices with the item-autofill pattern (§6.18–6.20), posting/voiding/payment with partial-payment support and the atomic settlement-reference counter (§4.9). Then the full Customer/Sales-Invoice mirror (§4.10, §6.23). Wire the bank-transaction-on-payment/receipt integration (both AP payments and AR receipts must also create a `bank_transactions` row per §4.7/§4.9/§4.10).

**Phase 6 — Budget, polish, packaging**
Budget list/new/detail with variance (§4.14, §6.24–6.26) — remember: no edit screen, by design. Then: implement the shared smart-select widget pattern (§7.1) as one reusable component and retrofit it everywhere an account/bank/vendor/customer/item is picked across every earlier phase's screens (if you built ad hoc pickers earlier for speed, consolidate them now). Apply the design tokens and bundle the three fonts locally (§7.4). Apply all three status-color systems exactly per-screen (§7.3). Finally, write and test a packaging script (`flet build windows` or PyInstaller) that produces one self-contained `.exe`, and verify the packaged build launches and creates its SQLite file correctly on a clean run.

## Verification expectations

Before declaring the build complete:
- Walk the entire PRD §12 checklist and mark each item, noting any that are incomplete or behave differently than specified.
- Manually exercise at least one full accounting cycle end-to-end in the running app: create accounts → post opening balances → create and post a manual journal entry → create a vendor, item, and AP invoice, post it, make a partial payment then a final payment → create a customer and AR invoice, post it, receive payment → create a bank account, record a transaction, run a reconciliation to completion → generate all four reports and confirm the balance sheet balances → export at least one report to PDF and one list to XLSX and confirm the files open correctly.
- Confirm the packaged `.exe` runs on a machine/VM without a separate Python installation.

## Final report

When you consider the build complete, report back with:
1. A completed/annotated copy of the PRD §12 checklist (done / not done / done-differently-because — with reasoning for any deviation).
2. Any place you deliberately deviated from the PRD (should be none, but call it out explicitly if it happened and why).
3. Any of the PRD §10 quirks you found yourself tempted to "fix," and confirmation you left them as-is.
4. Instructions for building and running the packaged `.exe`.
