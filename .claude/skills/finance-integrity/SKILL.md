---
name: finance-integrity
description: >
  Preserve StoreTrack finance, receivable, payable, CashAccount and
  FinancialTransaction integrity. Use when changes touch payments, sales,
  procurement, expenses, order completion, reversal, exports, or analytics.
version: "1.0"
updated: 2026-09-04
---

# Finance Integrity (StoreTrack)

## Principles

- `FinancialTransaction` describes actual money movement.
- `CashAccount` is the account/balance layer.
- Customer receivable and supplier payable status are settlement states, not
  production/procurement lifecycle status.
- Use `Decimal`; never floats for money.
- Historical money movements should normally be reversed with compensating
  entries rather than silently erased.
- A Sale generated from offcut allocation is a distinct sale/receivable from
  the original customer's Order.
- Production reversal must inspect later payments before automatically
  neutralizing a sale.

## Exports and analytics

Exports should use the same business-scoped query definition as the screen they
represent. Reversed/voided activity must be treated consistently between live
Finance tables and analytics.

## Review questions

- Does this action move cash or only create a receivable/payable?
- Is a payment being counted twice through both status and ledger logic?
- If reversed, is there an audit-preserving compensating transaction?
- Could deleting an account/record break historical references?
