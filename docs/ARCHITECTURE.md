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
    production/             ProductionRequest, ProductionOrder
    sales/                  Sale, SaleItem
  templates/                one dir per app, mirroring the apps/ split
  docs/
    ARCHITECTURE.md         this file
  CLAUDE.md                 agent instructions — read this first when editing
```

## Data flow

```
PurchaseOrder --(receive)--> RawMaterial.stock += qty, cost_per_unit updated
RawMaterial --(recipe)--> FinishedGood            (RecipeItem: qty per unit)
ProductionRequest --(fulfilled by)--> ProductionOrder
ProductionOrder --(complete)--> RawMaterial.stock -= recipe qty * order qty
                                  FinishedGood.stock += order qty
                                  linked ProductionRequest -> fulfilled
Sale --(save)--> FinishedGood.stock -= qty
```

Every stock-mutating step above runs inside `transaction.atomic()` and
checks for shortages first, with an explicit `force` override rather than a
silent negative-stock write.

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
is *routing* (deciding which business a request belongs to from the URL or
session) — see `CLAUDE.md` §7.

## Update this file when

- An app boundary changes (a model moves apps, or a new app is added)
- The Business/tenant pattern changes (e.g. real routing gets added)
- A new stock-mutating flow is added — extend the data-flow diagram above
