# Partial Payment Journal References Design

## Goal

Allow multiple partial AP payments and AR receipts against one posted invoice without violating the unique `JournalEntry.reference` constraint.

## Root Cause

AP payments use the fixed journal reference `APPay-<invoice number>` and AR receipts use `ARRec-<invoice number>`. A second transaction against the same invoice attempts to save the same globally unique `JournalEntry.reference`.

## Design

Add a shared reference generator in `banks.services`, alongside the existing atomic bank-transaction reference generator. It uses a Neo4j `MERGE` counter keyed by transaction family and invoice number, returning a readable sequence:

- `APPay-PI-2026-0002-0001`
- `APPay-PI-2026-0002-0002`
- `ARRec-SI-2026-0002-0001`

`record_payment` and `record_receipt` call this generator when constructing their journal entries. The existing invoice amount/status update logic remains unchanged.

## Testing

Unit tests mock the graph nodes and counter query, then call each service twice against the same posted invoice. They assert two distinct journal references are saved and the invoice remains posted after the first partial transaction before becoming paid after the final transaction.

## Constraints

- Reuse Neo4j atomic counters; add no dependency.
- Keep payment and receipt references readable and deterministic in shape.
- Do not alter existing bank-transaction reference generation or unrelated user changes.
