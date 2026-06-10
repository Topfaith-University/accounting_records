# SageOne UX Alignment — Design Spec
**Date:** 2026-06-10

## Goal
Bring Sage closer to SageOne's UX: smart selectors with inline creation, simplified journal entry form, dedicated Banking sidebar section, inline bank account creation, and general SageOne alignment across all pages.

---

## 1. Smart Account Selector (`AccountSelectComponent`)

**Scope:** Replaces every plain `<select>` that picks a GL account across the entire app.

**Behaviour:**
- Text input that filters accounts by code or name as the user types
- Dropdown list appears below input, showing matching accounts (`CODE — Name`)
- If no accounts match the typed text, a "+ Create account…" row appears at the bottom of the dropdown
- Clicking "+ Create account…" opens a small inline modal with: Name (required), Type (required, select from AccountType enum), Description (optional); Normal Balance is auto-derived from Type and shown as read-only
- On modal save, the account is created via `POST /api/accounts/`, the new account is selected automatically in the parent field, and the modal closes
- The component emits the selected `account_id` via `(accountChange)` output and accepts `[accountId]` as input for edit mode
- `[label]` input controls the field label; `[required]` input controls validation state

**Files:**
- `frontend/sage-frontend/src/app/shared/account-select/account-select.component.ts`
- `frontend/sage-frontend/src/app/shared/account-select/account-select.component.html`

**Integration points:** journal entry form lines, bank transaction splits, payables invoice form (AP account + expense account lines), receivables invoice form (AR account + income account lines), bank account GL account field in bank-account-list create form.

---

## 2. Smart Bank Account Selector (`BankSelectComponent`)

**Scope:** Replaces every plain `<select>` that picks a bank account.

**Behaviour:** Same pattern as AccountSelectComponent but for bank accounts.
- Filters by bank account name
- "+ Create bank account…" opens modal with: Account Name (required), Bank Name (required), Account Number, Opening Balance (₦), Opening Balance Date (required), GL Account (AccountSelect embedded inside this modal)
- On save: `POST /api/banks/`, new bank account selected automatically

**Files:**
- `frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.ts`
- `frontend/sage-frontend/src/app/shared/bank-select/bank-select.component.html`

**Integration points:** bank transaction form (source bank, destination bank for TRANSFER), bank reconciliation form.

---

## 3. Dedicated "Banking" Sidebar Section

**Change:** In `shell.component.html` and `shell.component.ts`:
- Rename "General Ledger" section to "Ledger" — keep Chart of Accounts and Journal Entries
- Remove Bank Accounts and Transactions from "Ledger"
- Add new "Banking" collapsible section with: Bank Accounts, Transactions, Reconciliation
- Banking section uses a distinct visual style (different accent color or icon) from Ledger

---

## 4. Simplified Journal Entry Form

**Change:** In `entry-form.component.html` / `.ts`:
- Replace `Account | Side (DEBIT/CREDIT) | Amount | Memo` columns with `Account | Debit (₦) | Credit (₦) | Memo`
- Each line has two amount fields instead of a side dropdown + one amount field
- A line is a debit entry if Debit amount > 0; credit entry if Credit amount > 0; only one can be non-zero per line
- Running totals still show total debits and total credits; balanced indicator unchanged
- Account column uses `AccountSelectComponent`

**Backend unchanged** — the serializer still receives `side` and `amount`; the frontend maps `(debit_amount > 0) → side=DEBIT, amount=debit_amount` and `(credit_amount > 0) → side=CREDIT, amount=credit_amount` before submission.

---

## 5. General SageOne Alignment

- **Confirm dialogs** on all Delete buttons (accounts, bank accounts, journal entries if draft, vendors, customers, invoices)
- **Empty-state messages** with CTA buttons on all list pages: "No X yet — [+ Create first X]"
- **Status badges** verified on AP/AR invoice lists (DRAFT / POSTED / PAID)
- **Button placement**: primary action (Save / Post / Create) always bottom-left of form; destructive action (Delete) always separated from Edit
- **Style consistency**: replace all hardcoded `background:white`, `border:1px solid #ccc`, `border-radius:4px`, `color:#555` inline styles in journal entry form and payables/receivables forms with project CSS variables (`var(--white)`, `var(--border)`, `var(--radius-sm)`, `var(--text-muted)`)
