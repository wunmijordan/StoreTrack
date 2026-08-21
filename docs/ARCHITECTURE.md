# Architecture

An index of how StoreTrack is put together, and why — written the same way
as ChurchForce's `docs/architecture/README.md`, scaled to a much smaller
system.

## Why this structure

The brief was: emulate a proven multitenant Django structure, but keep it
lightweight enough to start using immediately. The compromise:

- **Borrowed**: `apps/` layout, one Django app per domain, a shared base
  model hierarchy, a tenant-owned base model with a scoped manager resolved
  in middleware.
- **Deliberately not borrowed (yet)**: real tenant routing, permission
  tiers, dedicated per-tenant databases, Channels/Redis/Cloudinary, an AI
  skill registry. None of these earn their complexity at one business, one
  admin user, SQLite. `CLAUDE.md` §7 lists exactly what's missing and how
  to add it the same way ChurchForce did, when it's actually needed.

## Directory layout

```
storetrack/
  manage.py
  storetrack/              project package: settings, root urls, wsgi
  apps/                     domain apps (added to sys.path via settings.py)
    core/                   Business, BaseModel/TimestampedModel/BusinessOwnedModel,
                            middleware, dashboard, reports & backup
    inventory/              RawMaterial, FinishedGood, RecipeItem (bill of materials)
    procurement/            PurchaseOrder, PurchaseOrderItem
    production/             Order, OrderItem (customer orders & physical store restocks)
    sales/                  Sale, SaleItem
  templates/                one dir per app, mirroring the apps/ split
  docs/
    ARCHITECTURE.md         this file
  CLAUDE.md                 agent instructions — read this first when editing
```

## Data flow

```
PurchaseOrder --(receive)--> RawMaterial.stock += qty x total_conversion_factor
                              RawMaterial.cost_per_unit updated
RawMaterial --(recipe, per BATCH)--> FinishedGood     (RecipeItem: qty_per_batch)

Walk-in Sale --(save)--> FinishedGood.stock -= (batch_qty x units_per_batch + piece_qty)  [immediate]
                          price auto-filled from FinishedGood.selling_price, not entered

Order (customer or physical_store) --(created)--> status=pending, nothing touched yet
  --(approve)--> RawMaterial.stock -= exact batch+piece requirement per line item
                 (piece portion is proportional: qty_per_batch / units_per_batch x piece_qty —
                  no rounding up to a whole batch, no surplus production)
                 status=approved
  --(complete)--> FinishedGood.total_produced += total_units, always
                  IF order_type == physical_store: FinishedGood.stock += total_units
                  IF order_type == customer: stock untouched (delivered directly, never
                     shelved) — instead a Sale + SaleItem is created automatically
                     (source=customer_order), appearing on the Sales list
                  status=completed
  --(reject)--> only from pending, before any deduction — status=rejected
```

Every stock-mutating step above runs inside `transaction.atomic()`. Orders are
approved/completed as a whole (all line items together), not item-by-item.
Quantity is always entered as exact batches + pieces at order/sale time —
nothing downstream re-asks for or rounds it.

## The Business (tenant) pattern

```
Request
  -> BusinessMiddleware resolves Business.default() (one row today)
  -> request.business attached
  -> contextvar set (core.context)
  -> BusinessOwnedModel.objects (scoped manager) filters every query by it
  -> BusinessOwnedModel.raw_objects bypasses the filter (admin/shell only)
```

This is the one piece of real "future-proofing" in an otherwise
deliberately minimal system, because multi-location was flagged as a likely
next step. The day there's a second `Business` row, the scoping is already
correct — verified directly during development by creating a second
business, confirming `objects.all()` only sees its own rows, and confirming
`raw_objects.all()` sees both. What's still missing for real multi-location
is _routing_ (deciding which business a request belongs to from the URL or
session) — see `CLAUDE.md` §7.

## Update this file when

- An app boundary changes (a model moves apps, or a new app is added)
- The Business/tenant pattern changes (e.g. real routing gets added)
- A new stock-mutating flow is added — extend the data-flow diagram above
