# Customer Ordering and External Commerce Integration

## Architectural intent

StoreTrack should remain the system of record for tenant identity, products,
pricing, production, inventory, sales, receivables and cash. Customer-facing
ordering should be built into the same Django application and database, while
the same ordering capability is exposed through a stable integration boundary
for existing websites and third-party ordering platforms.

These are complementary entry points, not separate ordering systems:

```text
StoreTrack customer storefront ----+
                                    |
Existing business website ----------+--> Shared commerce/order service
                                    |             |
Third-party ordering platform ------+             v
                                          Existing production,
                                          inventory, sales and finance
```

The shared commerce service is responsible for tenant resolution, product and
quantity validation, server-side pricing, idempotency, customer/service data,
availability and routing. StoreTrack's own storefront can call it directly.
External systems call the same contract through an API or signed webhook.

External systems must never write directly to `production.Order`, `sales.Sale`,
stock balances or finance records. Direct writes could bypass price snapshots,
material release, batch costing, expiry, stock allocation, receivables and audit
rules.

## Supported ways to plug StoreTrack into another website

### 1. Hosted storefront

Each tenant can have a public path such as:

```text
https://app.example.com/shop/blue-kitchen/
```

An existing website only needs an **Order now** link. StoreTrack owns catalogue
validation and checkout, so the host website requires no complex integration.
This should be the first delivery because it has the lowest compatibility and
deployment risk.

### 2. Embeddable catalogue or order button

A small JavaScript component can display StoreTrack products on an existing
site. Checkout should still open the hosted StoreTrack route. The tenant's site
controls placement and presentation; StoreTrack remains authoritative for
prices, availability and order creation.

### 3. Headless API

Custom websites and mobile applications can consume a versioned contract:

```text
GET  /api/v1/storefronts/{business_slug}/products
POST /api/v1/storefronts/{business_slug}/orders
GET  /api/v1/storefronts/{business_slug}/orders/{public_id}
```

Order submission should require an idempotency key. Product and order
identifiers exposed publicly should be non-sequential UUIDs. Submitted totals
must be ignored and recalculated from StoreTrack pricing.

### 4. Platform connectors

Shopify-, WooCommerce- or restaurant-platform-style connectors translate each
provider's signed webhook payload into the same StoreTrack intake contract.
Provider order IDs must be unique per tenant/integration so retries cannot
create duplicate StoreTrack orders.

## Customer-order intake boundary

A public submission should first create a tenant-owned commerce intake record,
not immediately mutate production, shelf stock or finance. The intake record
can contain:

- public order UUID and customer-facing number;
- source/integration and external order ID;
- customer/contact snapshot;
- requested products and quantities;
- StoreTrack-calculated price snapshots;
- service mode, table/reference, delivery or pickup details;
- payment state kept separately from fulfilment state;
- links to the accepted production order, sale and customer record;
- pending-review, accepted, rejected, cancelled and fulfilled states.

A separate storefront-product record can control publication, description,
image, minimum/maximum quantity, lead time and fulfilment policy without
changing the existing `FinishedGood` master. Existing products should default
to unpublished, preserving live data and current back-office flows.

## Routing accepted demand

```text
Customer order intake
        |
        +--> Made to order --> Pending Production Order
        |                         |
        |                         +--> approval releases materials
        |                         +--> completion records batch/cost
        |                         +--> Sale / receivable / cash
        |
        +--> Distribution Market Stock available
        |                         |
        |                         +--> FEFO lot allocation
        |                         +--> Distribution Sale
        |
        +--> Physical stock available
                                  |
                                  +--> reservation / fulfilment
                                  +--> Sale and stock deduction
```

The acceptance policy is tenant and vertical aware:

- Bakery orders can route to scheduled Online/Distribution production or
  available stock.
- Restaurant orders retain dine-in, takeaway/delivery and table/service
  references; catering/bulk demand uses the stable Distribution channel.
- General production can use pending review, quotation and lead-time policies.
- Wholesale routes accepted demand against procured warehouse stock using the
  stable Distribution channel, preserving trade-customer pricing, credit terms,
  receivables and payments without invoking Production.
- Retail routes accepted demand against procured shop stock as an immediate
  Physical Store/POS sale, with supplier arrivals traced through received POs.
- Established wholesale customers can retain customer-specific prices and
  terms; ad-hoc online customers can remain snapshots until deliberately added
  to the customer master.

Payment-provider confirmation should flow into the existing payment and finance
models. A browser redirect is not proof of payment. Payment and fulfilment must
remain independent states.

## Distribution Market Stock integration

`FinishedGood.stock` represents Physical Store stock and cannot safely answer
public Distribution availability. StoreTrack therefore maintains separate,
batch-aware Distribution Market Stock lots.

New unassigned Distribution production flows as follows:

```text
Market-stock Production Order
        --> approval / material release
        --> completion / ProductionBatch / frozen cost / expiry
        --> Distribution Market Stock lot
```

The lot retains batch, quantity, expiry date and frozen unit cost. Customer
release uses first-expiry-first-out allocation and creates an ordinary
Distribution `Sale`, so existing sales, receivable, payment and profitability
reporting continue to work.

Redistributable customer returns become new Market Stock lots while preserving
the original production batch and expiry date. Damaged returns are unsellable
and reported at frozen unit cost. Expired quantities are automatically excluded
from allocation and Physical Store transfer; reconciliation closes the lot and
records the non-cash inventory-loss value.

Unsold Market Stock can be transferred explicitly into Physical Store stock.
For a product normally unavailable in the Physical Store, the transferred
quantity is a narrow shelf-sale allowance. It does not silently change the
product's normal shelf configuration, and shelf sales consume that allowance.

Existing planned offcut, additional excess, production wastage and shortage
reconciliation retain their established semantics. They are not silently
merged into the Market Stock balance. The sole exception is additional excess
on an unassigned Distribution market-stock order: its completion form requires
that amount to be allocated explicitly to Market Stock (or to a stated
non-stock purpose), never directly to the Physical Store shelf.

## Tenant routing without subdomains

Subdomains and custom domains are not required. Back-office requests use the
authenticated user's active `UserBusiness` membership. All businesses can use
one login host and the same internal paths.

Anonymous storefront requests do not have a staff membership session, so their
tenant must be explicit in the public path:

```text
https://app.example.com/shop/blue-kitchen/
https://app.example.com/shop/jordan-bakery/
```

The globally unique `Business.slug` identifies the tenant. API credentials and
webhook configurations must also resolve to exactly one Business; a caller must
never be allowed to submit an arbitrary `business_id`.

Optional subdomains or custom domains can later be aliases:

```text
blue-kitchen.app.example.com
orders.bluekitchen.com
```

A future business-domain mapping can translate either hostname to the same
tenant/storefront. DNS, TLS and allowed-host configuration are deployment
concerns; they do not require separate applications or databases.

## SQLite and PythonAnywhere rollout

The initial design remains a Django monolith using SQLite:

- use short `transaction.atomic()` operations;
- enforce idempotency with unique constraints;
- do not make external HTTP calls while a database transaction is open;
- store inbound/outbound webhook attempts for retry and audit;
- use a PythonAnywhere scheduled management command for retries if required;
- apply rate limits and signed webhook verification;
- release behind a tenant/module preference and default storefront products to
  unpublished.

There is no fixed application-level tenant count. Practical capacity is bounded
by concurrent SQLite writes, database/media size, traffic, reports and hosting
worker limits. The domain and API contracts should remain stable if operational
scale later requires PostgreSQL.

## Safe implementation order

1. Extract reusable commerce/order services from form views.
2. Add commerce intake and storefront-product models through additive
   migrations.
3. Keep storefronts disabled and products unpublished by default.
4. Pilot hosted ordering with pending staff review for one tenant.
5. Add physical-stock reservation before promising stock fulfilment publicly.
6. Add the embeddable component and versioned API.
7. Add provider connectors and payment integrations incrementally.

The safest first public release is **hosted order -> pending review -> existing
production or Market Stock flow**. Existing bakery, restaurant and general
back-office behavior remains unchanged until a tenant enables the new channel.
