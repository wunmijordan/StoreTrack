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

## Accounting and audit layer

StoreTrack now separates physical stock movement, product costing, recognised
revenue, and actual cash movement.

- `StockMovement` is the physical inventory ledger and carries a reference,
  unit value and optional inventory location.
- `StockAdjustment` records count corrections, wastage, damage, returns,
  internal use, staff issues and charity/donation issues without silently
  changing stock.
- `ProductionCostSnapshot` freezes historical production cost using the latest
  received procurement price available on the production date; no weighted
  averaging is used.
- `Sale.transaction_type` distinguishes paid sales from unpaid product issues.
  Unpaid sales reduce stock and remain visible as non-cash product value.
- Physical-store unpaid production orders first record production into shelf
  stock and immediately record the outgoing product issue, so the physical
  stock ledger remains fully explainable.
- `FinancialTransaction` is the actual money-in/money-out ledger.
- `CashAccount` provides cash/bank/POS balances.
- `SupplierPayment` and `CustomerPayment` provide explicit settlement records.
- `AuditLog` records important operational mutations.

## Cost/profit/cash distinction

The dashboard treats these as separate concepts:

```
Sales revenue (paid transactions)
        - historical COGS
        = Gross profit

Cash received - actual cash outflows
        = Net cash flow

Unpaid product issues
        = non-cash product value (tracked separately)
```

Procurement and expenses marked unpaid are not counted as realised cash
outflow. Existing records default to paid so upgrading an existing database
does not change its historical totals unexpectedly.

## Operational supply dispensing and financial settlement

Operational supplies are RawMaterials with category `operational_supply`. They are procured through the normal Purchase Order flow and therefore increase raw-material stock when a PO is received, regardless of whether the supplier has been paid. They are intentionally excluded from FinishedGood recipes/production materials.

A manual Operational Supply Dispense records a dated reasoned issue in the material's usage unit and creates a `StockMovement.OPERATIONAL_DISPENSE` entry. This reduces stock and therefore participates in the normal reorder/warning logic. It is inventory consumption, not a second cash expense; the procurement that brought the supply into inventory remains the financial acquisition event.

Customer Distribution/Online orders are treated as receivables after completion. Their Sales records begin unpaid and can move to partial/paid through Finance > Customer Payment. Physical Store unpaid transactions are different: they represent non-cash product issues (for example staff or charity) and remain explicitly reasoned on the physical-store transaction.

Supplier procurement is also split between inventory recognition and cash settlement. Receiving a PO always records inventory and the historical procurement price. A paid PO records its cash outflow at receipt; an unpaid/partial PO remains a payable until Supplier Payment entries are recorded in Finance. Financial analytics therefore distinguish received procurement value from actual procurement cash paid.

CashAccount records represent real cash/bank/card locations. New paid sales, paid procurement and paid expenses require an account selection; later customer/supplier payments also require an account. This keeps the cash ledger reconcilable to real-world balances.

Customer and supplier payment forms only expose outstanding Distribution/Online sales and received unpaid/partial purchase orders respectively. Selecting a customer or supplier document populates the associated document and outstanding amount for review before posting the payment.


## Access control and payment timing

The application uses a custom `accounts.CustomUser` with a single full-name field plus
username, email, phone and a business role. `UserBusiness` scopes membership to a
business, and `UserModulePermission` provides per-user View/Edit permissions for each
application module. The live Users & Access screen is the normal administration path;
Django admin remains reserved for true superusers.

Payment state is intentionally separated by transaction context:
- Physical Store orders/sales use `transaction_type` for Paid shelf stock versus
  Unpaid non-cash issues.
- Distribution/Online production orders use `customer_payment_status` for Paid at
  Request versus Pay Later. A payment marked paid at request creates the cash/bank
  ledger entry immediately; a later payment creates a CustomerPayment and cash entry.
- Procurement and Expenses use `payment_status`. Paid procurement/expenses record
  cash at request, while unpaid records remain payables until Finance settles them.
- Receiving a procurement always changes raw-material stock and creates the historical
  procurement cost snapshot regardless of payment status.
