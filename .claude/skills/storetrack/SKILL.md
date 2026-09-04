---
name: storetrack
description: >
  Full StoreTrack project reference for implementation prompts. Use when a task
  spans multiple apps, changes production/commercial behaviour, or CLAUDE.md is
  not enough context. Covers tenant isolation, proportional recipes, shared
  production runs, inventory, finance, reversals, and safe extension rules.
version: "1.0"
updated: 2026-09-04
---

# StoreTrack — Full Project Skill

Use this skill when implementing or reviewing a change that crosses app
boundaries or could affect inventory, production, sales, finance, tenancy, or
historical traceability.

## 1. Product identity

StoreTrack is a multi-business production-aware commercial management system
for businesses that procure materials, manufacture/prepare products, manage
finished inventory, sell through several channels, and track the resulting
cash, payables and receivables.

Current apps:

| App | Responsibility |
| --- | --- |
| `core` | Business tenant, scoped base models/managers, middleware, dashboard, finance, reports |
| `accounts` | CustomUser, Role, UserBusiness, module permissions |
| `inventory` | RawMaterial, FinishedGood, recipe/BOM, production materials, stock movements, market stock |
| `procurement` | PurchaseOrder and supplier-side procurement flows |
| `production` | Orders, Shared Production Runs, material release, batches, QC, offcuts, reconciliation, reversal |
| `sales` | Customer master, sales, pricing, customer payments |
| `expenses` | Expenses and expense payment records |

## 2. Tenant rule

`core.models.Business` is the tenant root.

Most top-level tenant data must inherit `BusinessOwnedModel`.

In request code:

- use `Model.objects`, not `Model.raw_objects`;
- rely on `request.business` resolved by `BusinessMiddleware`;
- set `obj.business = request.business` before saving a new
  `BusinessOwnedModel`;
- never trust a posted business ID;
- line items that are already scoped through a tenant-owned parent normally do
  not need their own business FK.

Superuser cross-business access is explicit. Ordinary users must never see or
mutate another business's data.

## 3. Quantity and recipe semantics

A registered product recipe describes one reference batch and yield. Material
usage is proportional to the actual planned product quantity; an order does
**not** consume a whole reference batch merely because the recipe is batch
based.

Example:

```text
FAO Mini Loaves
registered yield = 110 pcs
flour per reference batch = 20 kg

planned quantity = 50 pcs
flour requirement = 50 / 110 * 20 kg
```

Keep `Decimal` arithmetic. Never introduce floats into recipe, stock, price or
cost calculations.

Flexible recipe ingredients are still proportional: the override changes the
per-reference-batch quantity, then the ordinary production multiplier applies.

## 4. Production Order semantics

An `Order` is a commercial/production request. Distribution and Online orders
retain the customer's requested quantity even when production intentionally
plans more units.

Per item distinguish:

- ordered/customer quantity;
- planned production quantity;
- actual gross output;
- wastage;
- saleable output;
- customer shortage;
- planned offcut;
- additional/unplanned excess.

Do not rewrite customer demand to match physical output.

## 5. Shared Production Runs

`ProductionRun` is an optional coordination layer above ordinary pending
orders. It does not replace the Order model or its recipe engine.

A run can be assembled by:

1. attaching existing Pending orders; and/or
2. creating new orders from the Draft run using the normal Order form.

Approval of a run:

1. calculates each member OrderItem using the same proportional recipe logic
   as ordinary approval;
2. applies flexible recipe quantities at item level;
3. aggregates identical RawMaterial requirements across member orders;
4. performs one combined stock check/release;
5. writes `OrderMaterialUsage` per order item so costing remains attributable;
6. marks all member orders Approved together.

While a Pending order belongs to a Draft run, individual approval must remain
blocked to prevent double release.

The legacy `ProductionRunMaterial` model is retained for compatibility only;
new Shared Runs do not use run-level common-material substitution.

## 6. Completion, offcuts, and excess

Production completion is atomic and records the physical result.

For customer orders:

- customer-required units are fulfilled first;
- saleable units between customer requirement and planned production target
  are **planned offcut**;
- planned offcut may be allocated to multiple Distribution/Online customers;
- any uncommitted planned offcut automatically becomes general FinishedGood
  stock;
- saleable units above the planned target are additional excess and use the
  explicit excess allocation path;
- saleable units below customer requirement create a shortage.

Each offcut customer allocation has its own customer, channel, quantity and
Sale/receivable. Do not fold these into the original customer's invoice.

## 7. Shortage reconciliation

Shortage reconciliation may use available stock/surplus of the same finished
product regardless of the originating production channel.

Recheck both:

- traceable available surplus on the source batch; and
- live FinishedGood stock.

Do not create a duplicate sale or duplicate production event when satisfying an
already-existing customer shortage.

## 8. Reversal and deletion

A completed order is not safely corrected by deleting it.

Use the compensating reversal flow so StoreTrack can restore/reverse:

- exact raw-material usage snapshots;
- reversible FinishedGood stock;
- customer-delivery totals;
- associated sales/offcut allocations;
- applicable cash ledger effects.

Block reversal when downstream state makes automatic reversal unsafe, such as
used reconciliation sources or subsequent customer payments.

A reversed order is historical. `Edit as New Order` creates a fresh Pending
copy using the normal current Order form. Permanent deletion is allowed only
from the Reversed state.

## 9. Business-specific Order numbering

`Order.id` is a global technical database key.

`Order.order_number` is the visible business-local number and is unique by
`(business, order_number)`.

Never replace URLs/FKs with `order_number` alone. Tenant-specific sequence
reset must not reset global PK sequences or other tables.

## 10. Inventory rules

- RawMaterial stock supports 3 decimal places end-to-end.
- FinishedGood stock remains the authoritative live finished-stock total.
- The uncommitted-offcut indicator is a traceable subset/pool, not a second
  stock ledger.
- Stock mutations must use existing stock movement services/records and run
  within `transaction.atomic()`.
- Never silently allow negative stock; preserve explicit force/override flows.

## 11. Pricing rules

Distribution/Online price resolution:

```text
Customer + Product + Channel
        -> Product + Channel
        -> FinishedGood default price
```

Physical Store does not use customer-specific price.

New/dynamic formset rows must resolve price exactly like the initial row.
Server-side resolution remains authoritative and the resolved price is
snapshotted on the order item.

## 12. Finance rules

`FinancialTransaction` is the money movement ledger; `CashAccount` is the
balance/account layer.

Prefer compensating entries to destructive edits for historical financial
transactions. Keep receivable/payable states distinct from physical production
status.

Finance, sales and production analytics must exclude/neutralize reversed
activity according to the existing reversal design rather than deleting
history opportunistically.

## 13. User/role visibility

Normal Business Admin user lists exclude Django superusers and roles where
`visible_to_admin=False`. A Django superuser can see all users/roles in the
business-management view.

Do not convert this visibility property into an authorization boundary: actual
permissions still come from role/module/user permissions.

## 14. Implementation checklist

Before editing:

- identify every app touched by the business transaction;
- inspect the latest migration head before naming a migration;
- identify existing transaction boundaries and stock movement helpers;
- check tenant scope on every queryset/create;
- check whether historical snapshots or reversal logic must also change.

After editing:

- run `python manage.py check`;
- compile/import changed Python modules;
- run/review migrations;
- smoke-test relevant happy path plus validation failure;
- for production changes, trace approve -> material usage -> complete -> batch ->
  stock/sale -> finance -> reversal;
- run the `simplify` and `tenant-safety` skills.
