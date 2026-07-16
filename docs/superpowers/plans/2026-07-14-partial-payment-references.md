# Partial Payment Journal References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate unique journal-entry references for every partial AP payment and AR receipt.

**Architecture:** A single Neo4j-backed reference generator increments a counter scoped to journal-reference family and invoice number. AP and AR services call it before saving their journal entry, leaving invoice balances and bank-transaction references unchanged.

**Tech Stack:** Django, neomodel/Neo4j Cypher counters, Django `TestCase`, `unittest.mock`.

## Global Constraints

- Reuse Neo4j atomic counters; add no dependency.
- Preserve readable reference prefixes: `APPay-` and `ARRec-`.
- Do not change existing bank-transaction reference generation or unrelated user changes.

---

### Task 1: Shared Journal Reference Generator

**Files:**
- Modify: `backend/banks/tests.py`
- Modify: `backend/banks/services.py`

- [ ] **Step 1: Write failing counter tests**

  Mock `banks.services.db.cypher_query`, call `generate_invoice_settlement_reference('APPay', 'PI-2026-0002')`, and assert it returns `APPay-PI-2026-0002-0001` for counter result `[[1]]`; assert `[[2]]` returns suffix `0002`.

- [ ] **Step 2: Verify RED**

  Run: `cd backend && venv/bin/python manage.py test banks.tests.GenerateInvoiceSettlementReferenceTests -v 2`

  Expected: FAIL because `generate_invoice_settlement_reference` does not exist.

- [ ] **Step 3: Implement the generator**

  Add this to `backend/banks/services.py`:

  ```python
  def generate_invoice_settlement_reference(prefix: str, invoice_number: str) -> str:
      results, _ = db.cypher_query(
          """
          MERGE (c:InvoiceSettlementCounter {prefix: $prefix, invoice_number: $invoice_number})
          ON CREATE SET c.seq = 1
          ON MATCH SET c.seq = c.seq + 1
          RETURN c.seq
          """,
          {'prefix': prefix, 'invoice_number': invoice_number},
      )
      return f'{prefix}-{invoice_number}-{int(results[0][0]):04d}'
  ```

- [ ] **Step 4: Verify GREEN**

  Run: `cd backend && venv/bin/python manage.py test banks.tests.GenerateInvoiceSettlementReferenceTests -v 2`

  Expected: PASS.

### Task 2: AP and AR Partial-Settlement Regression

**Files:**
- Modify: `backend/payables/services.py`
- Modify: `backend/payables/tests.py`
- Modify: `backend/receivables/services.py`
- Modify: `backend/receivables/tests.py`

- [ ] **Step 1: Write failing service tests**

  Mock each service's graph dependencies and `generate_invoice_settlement_reference`. Call `record_payment` twice for one posted invoice and assert its two saved `JournalEntry` objects receive `APPay-PI-2026-0002-0001` and `APPay-PI-2026-0002-0002`. Repeat for `record_receipt` with `ARRec-SI-2026-0002-0001` and `ARRec-SI-2026-0002-0002`.

- [ ] **Step 2: Verify RED**

  Run: `cd backend && venv/bin/python manage.py test payables.tests.RecordPaymentReferenceTests receivables.tests.RecordReceiptReferenceTests -v 2`

  Expected: FAIL because the fixed invoice-only references remain in use.

- [ ] **Step 3: Replace fixed references**

  In `record_payment`, import the shared generator and set:

  ```python
  reference=generate_invoice_settlement_reference('APPay', invoice.invoice_number)
  ```

  In `record_receipt`, set:

  ```python
  reference=generate_invoice_settlement_reference('ARRec', invoice.invoice_number)
  ```

- [ ] **Step 4: Verify GREEN**

  Run: `cd backend && venv/bin/python manage.py test banks.tests.GenerateInvoiceSettlementReferenceTests payables.tests.RecordPaymentReferenceTests receivables.tests.RecordReceiptReferenceTests -v 2`

  Expected: PASS.

- [ ] **Step 5: Run affected package tests**

  Run: `cd backend && venv/bin/python manage.py test banks payables receivables -v 2`

  Expected: new focused tests pass; report any database-environment failures separately.
