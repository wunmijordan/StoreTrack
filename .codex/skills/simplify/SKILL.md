---
name: simplify
description: >
  Review changed StoreTrack code for reuse, correctness, efficiency, tenant
  safety, and consistency with existing domain flows; fix issues before
  presenting the implementation.
version: "1.0"
updated: 2026-09-04
---

# Simplify (StoreTrack)

Run after every implementation.

## Checklist

1. **Duplicated logic** — reuse existing price, stock, recipe, payment and
   permission helpers instead of creating parallel implementations.
2. **Single responsibility** — split views/helpers that mix validation,
   accounting and rendering unnecessarily.
3. **N+1 queries** — add `select_related` / `prefetch_related` where lists or
   detail pages traverse customers, products, batches or allocations.
4. **Dead imports / variables / stale fields** — especially after migrations or
   compatibility refactors.
5. **Decimal correctness** — no float arithmetic for stock, quantities, money,
   yield or cost.
6. **Atomic mutations** — procurement receipt, production release/completion,
   sales, payments and reversals remain transactional.
7. **Tenant isolation** — no `raw_objects` in request views; creates set
   `business`; posted IDs are re-queried through scoped managers.
8. **Historical integrity** — do not overwrite snapshots that should remain
   frozen; use compensating records for reversals.
9. **Formset cloning** — dynamic rows need correct management-form counts,
   prefixes, event binding, defaults and validation rendering.
10. **Backward compatibility** — legacy fields/models retained for migrated
    data must still render safely even if new flows use a newer structure.

Fix problems found; do not merely list them.
