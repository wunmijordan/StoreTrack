---
name: code-reviewer
description: >
  Deep review of StoreTrack Python, Django templates and vanilla JavaScript.
  Use before packaging a substantial feature or whenever a changed file is
  large, transaction-heavy, or crosses production/inventory/finance domains.
version: "1.0"
updated: 2026-09-04
---

# Code Reviewer (StoreTrack)

Review changed code against StoreTrack's actual architecture rather than a
generic Django checklist.

## Correctness

- Model declarations match migration state.
- Form/formset prefixes and management forms are correct.
- Dynamic rows initialise defaults and event handlers correctly.
- Decimal precision is preserved for stock, quantities and money.
- User-visible Order # uses business-local `order_number`; internal relations
  continue using PKs.

## Data integrity

- Stock mutations are atomic and create the expected movement/audit records.
- Production release quantities agree with `OrderMaterialUsage` and costing.
- Shared Run approval cannot double-release a member order.
- Offcut, shortage and excess are mutually understandable and not double
  counted in delivery/stock analytics.
- Reversal uses compensating operations and respects downstream dependencies.

## Tenant/security

- Request querysets use scoped `.objects`.
- New BusinessOwnedModel rows set `business` server-side.
- Related IDs from POST/GET are re-queried under tenant scope.
- Business Admin visibility restrictions do not weaken permission enforcement.

## Performance and maintainability

- Avoid N+1 traversal in dashboard, list, batch and finance views.
- Reuse pricing, stock and requirement helpers.
- Remove dead compatibility code only when migrations/data make it safe.
- Keep views readable; extract calculation/planning helpers when transaction
  code becomes difficult to audit.

Finish by running `simplify`, `tenant-safety`, and the domain skill relevant to
the change.
