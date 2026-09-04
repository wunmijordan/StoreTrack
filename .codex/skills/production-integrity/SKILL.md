---
name: production-integrity
description: >
  Preserve StoreTrack production, recipe, batch, stock, offcut, shortage,
  Shared Run, QC, costing and reversal invariants. Use for any production or
  inventory-mutating implementation.
version: "1.0"
updated: 2026-09-04
---

# Production Integrity (StoreTrack)

## Core invariants

### Recipe proportionality

A reference batch is a recipe/yield standard, not a minimum release quantity.
Requirement = planned product quantity / batch yield * configured batch input.

### Commercial demand vs production plan

Never conflate:

- customer requested quantity;
- planned production target;
- actual saleable output.

### Shared Production Runs

A Shared Run aggregates ordinary proportional requirements from multiple
Pending orders. It does not substitute a run-level recipe. Approval happens
once for all members; member orders cannot independently approve while the run
is Draft.

### Completion order

For a customer product:

1. calculate saleable = gross - wastage;
2. fulfil original customer up to requested quantity;
3. planned offcut = saleable between requested quantity and planned target;
4. allocate planned offcut across zero or more interested customers;
5. automatically retain uncommitted planned offcut as general stock;
6. additional excess = saleable above planned target;
7. shortage = requested quantity not fulfilled.

### Stock/cost snapshots

Material release and costing must agree. If a quantity is overridden (e.g.
flexible yeast), both stock deduction and `OrderMaterialUsage`/cost snapshots
must use the same actual quantity.

### Reversal

Never reverse by deleting stock movements. Use compensating movements and block
unsafe reversal where downstream reconciliation/payments make history dependent
on the completed order.

## Required smoke path

For production changes, verify at least:

```text
Pending Order
 -> Approve (or Shared Run Approve)
 -> RawMaterial movements
 -> Complete
 -> ProductionBatch + QC/cost snapshot
 -> customer Sale and/or FinishedGood stock
 -> optional reconciliation/offcut sale
 -> reversal eligibility
```
