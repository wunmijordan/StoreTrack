# StoreTrack Website Commerce Checkout Integration

This is the integration contract for a bakery/restaurant website using StoreTrack as its commerce and operations backend.

## Core invariant

**A new website integration must not create a `CommerceIntake` until StoreTrack has verified full payment.**

The website first creates a tenant-scoped checkout session. StoreTrack validates the basket, snapshots authoritative prices, and reserves immediate Physical Store stock where required. Payment is then initialized against that checkout. Only a verified full payment atomically materializes exactly one `CommerceIntake`.

Legacy `POST /orders` remains available during migration, but it creates an intake before payment and should not be used for new website checkout work.

## Authentication

For the headless API, send the tenant integration key on authenticated commerce requests:

```http
X-StoreTrack-Key: <tenant integration API key>
```

Never put StoreTrack gateway credentials on the website. Paystack/Monnify webhooks terminate directly at StoreTrack.

## 1. Fetch the catalogue

```http
GET /api/v1/storefronts/{business_slug}/products
```

The response contains each published product and the enabled `order_modes`. Prices, quantity limits, fulfilment mode, lead time, and `available_now` come from StoreTrack. `available_now` already excludes active StoreTrack checkout reservations.

Example product fragment:

```json
{
  "id": "7ea4b6b1-3c5a-4de1-9aba-3a7d28d3b810",
  "name": "Mini Loaf",
  "available_now": "18.00",
  "order_modes": [
    {
      "code": "physical_store",
      "label": "Physical Store",
      "price": "1000.00",
      "min_quantity": "1.00",
      "max_quantity": null,
      "fulfilment_mode": "stock",
      "available_now": "18.00",
      "lead_time": ""
    },
    {
      "code": "online",
      "label": "Online",
      "price": "950.00",
      "min_quantity": "5.00",
      "max_quantity": null,
      "fulfilment_mode": "preorder",
      "available_now": null,
      "lead_time": "24 hours"
    }
  ]
}
```

The website should render StoreTrack's labels and prices and send only product UUIDs and quantities back. Browser-submitted prices are never authoritative.

## 2. Discover payment methods

```http
GET /api/v1/storefronts/{business_slug}/payment-methods
X-StoreTrack-Key: <key>
```

Example:

```json
{
  "currency": "NGN",
  "methods": [
    {"code": "paystack", "label": "Paystack"},
    {"code": "bank_transfer", "label": "Bank transfer"}
  ]
}
```

Only methods that are both enabled and fully configured for that tenant are returned. Provider secrets, API keys, account credentials, and private gateway configuration are never exposed.

Eligibility is rechecked again when payment is initialized.

## 3. Create a checkout session

```http
POST /api/v1/storefronts/{business_slug}/checkouts
X-StoreTrack-Key: <key>
Idempotency-Key: website-checkout-2026-000123
Content-Type: application/json
```

Request:

```json
{
  "external_order_id": "WEB-ORDER-8821",
  "order_mode": "physical_store",
  "customer": {
    "name": "Ada Customer",
    "email": "ada@example.com",
    "phone": "+2348000000000",
    "address": "12 Example Street"
  },
  "service_mode": "delivery",
  "table_reference": "",
  "items": [
    {
      "product_id": "7ea4b6b1-3c5a-4de1-9aba-3a7d28d3b810",
      "quantity": "2"
    }
  ]
}
```

StoreTrack validates server-side:

- business/tenant scope;
- publication;
- selected order mode;
- minimum and maximum quantity;
- current channel price;
- current sellable stock and active reservations;
- the tenant's insufficient-stock policy.

No `CommerceIntake`, Sale, or Production Order exists at this point.

Successful response:

```json
{
  "checkout_id": "649948bd-613f-4d72-821e-7d99ae066d52",
  "status": "awaiting_payment",
  "order_mode": "physical_store",
  "fulfilment_mode": "stock",
  "amount": "2000.00",
  "currency": "NGN",
  "reservation_expires_at": "2026-09-07T15:45:00+01:00",
  "payment_status": null,
  "order": null,
  "created": true,
  "payment_methods_url": "/api/v1/storefronts/my-business/payment-methods",
  "payment_url": "/api/v1/storefronts/my-business/checkouts/649948bd-613f-4d72-821e-7d99ae066d52/payments"
}
```

### Minimum quantity error

HTTP `400`:

```json
{
  "detail": "Distribution requires at least 20.00 units for this order mode.",
  "code": "minimum_not_met",
  "suggested_order_modes": [
    {"code": "physical_store", "label": "Physical Store"},
    {"code": "online", "label": "Online"}
  ]
}
```

The website should let the customer choose one of the suggested modes and create a new checkout with a new idempotency key.

### Insufficient stock error / invite to preorder

HTTP `409`:

```json
{
  "detail": "Insufficient stock. The customer may switch to a Pre-order mode before paying.",
  "code": "insufficient_stock",
  "suggested_order_modes": [
    {"code": "online", "label": "Online"}
  ],
  "items": [
    {
      "product_id": "...",
      "product": "Mini Loaf",
      "requested": "20.00",
      "available_now": "8.00",
      "shortfall": "12.00"
    }
  ]
}
```

The exact behavior follows the tenant policy:

- `reduce`: checkout payable quantity is reduced to available stock and only that reduced quantity is charged;
- `reject`: no checkout is created;
- `invite_preorder`: no payable checkout is created; the response suggests applicable preorder modes;
- `split`: the available stock portion is reserved and the balance is retained as production demand under the existing split policy.

## 4. Initialize payment against the checkout

```http
POST /api/v1/storefronts/{business_slug}/checkouts/{checkout_uuid}/payments
X-StoreTrack-Key: <key>
Idempotency-Key: payment-attempt-8821-1
Content-Type: application/json
```

Paystack / Monnify request:

```json
{
  "method": "paystack",
  "return_url": "https://bakery.example.com/checkout/return"
}
```

Gateway response includes an authorization URL:

```json
{
  "payment_id": "...",
  "method": "paystack",
  "status": "awaiting_customer",
  "amount": "2000.00",
  "currency": "NGN",
  "reference": "STP-...",
  "authorization_url": "https://checkout.paystack.com/...",
  "checkout_id": "649948bd-613f-4d72-821e-7d99ae066d52",
  "order_id": null
}
```

Redirect the browser to `authorization_url`. The eventual browser redirect back to the website is **not proof of payment**. StoreTrack confirms the gateway transaction server-side after the signed provider webhook and provider verification call. Paystack webhooks are signature checked and verified against Paystack; Monnify notifications are signature checked in production and the transaction is independently verified against Monnify before value is granted.

### Bank transfer

```json
{
  "method": "bank_transfer"
}
```

Response:

```json
{
  "status": "pending",
  "reference": "STP-...",
  "bank_account": {
    "bank_name": "Example Bank",
    "account_name": "Example Bakery Ltd",
    "account_number": "0123456789"
  },
  "instructions": "Use the checkout/payment reference when transferring..."
}
```

After the customer transfers, submit evidence/claim data:

```http
POST /api/v1/storefronts/{business_slug}/checkouts/{checkout_uuid}/payments/current/claim
```

```json
{
  "payer_name": "Ada Customer",
  "transfer_reference": "BANK-TRX-992288"
}
```

This only changes the payment to `awaiting_verification`. It does not confirm funds and does not create an intake. Authorized StoreTrack staff must verify the actual bank credit.

### Cash

Cash remains `pending` until an authorized StoreTrack Business Admin or Finance editor confirms actual receipt. Browser/API submission cannot self-confirm cash.

## 5. Poll checkout/payment status

Before an order exists:

```http
GET /api/v1/storefronts/{business_slug}/checkouts/{checkout_uuid}/payments/current
X-StoreTrack-Key: <key>
```

Response shape:

```json
{
  "checkout": {
    "checkout_id": "...",
    "status": "awaiting_payment",
    "payment_status": "awaiting_customer",
    "order": null
  },
  "payment": {
    "payment_id": "...",
    "status": "awaiting_customer",
    "amount": "2000.00",
    "balance": "2000.00"
  }
}
```

Checkout status values:

- `awaiting_payment` — validated; no verified full payment yet;
- `paid` — full payment is verified and materialization is in progress;
- `materialized` — exactly one `CommerceIntake` exists;
- `paid_review` — real full payment exists, but the reservation expired or safe materialization failed; staff review/recovery is required;
- `expired` — unpaid checkout expired and its reservation was released;
- `cancelled` — checkout was cancelled.

Payment status values remain separate:

- `pending`;
- `awaiting_customer`;
- `awaiting_verification`;
- `partially_paid`;
- `paid`;
- `failed`;
- `cancelled`;
- `refunded`.

## 6. Transition from checkout UUID to order UUID

After StoreTrack verifies the full amount, it materializes the intake atomically and the checkout status response becomes:

```json
{
  "checkout_id": "649948bd-613f-4d72-821e-7d99ae066d52",
  "status": "materialized",
  "payment_status": "paid",
  "order_id": "e5ef6a60-bdb1-40a4-b2e3-d70a98147fb8",
  "order_number": "WEB-000124",
  "order": {
    "id": "e5ef6a60-bdb1-40a4-b2e3-d70a98147fb8",
    "number": "WEB-000124",
    "status": "pending",
    "payment_state": "confirmed",
    "fulfilment_state": "pending"
  }
}
```

`order.id` is the public UUID used for API status lookups. `order.number` is the tenant-local human display number. Do not treat them as interchangeable.

Once `order.id` exists, the existing order status endpoint remains available:

```http
GET /api/v1/storefronts/{business_slug}/orders/{order_uuid}
X-StoreTrack-Key: <key>
```

It reports order/intake status, payment state, fulfilment state, and item fulfilment separately.

## Reservation and late-payment behavior

Physical Store stock is reserved when a stock checkout is created. The hold lasts `CommerceSettings.checkout_reservation_minutes` (default 15 minutes, configurable 5–120 minutes).

Active reservations are deducted from `available_now` for later web checkouts. StoreTrack direct/POS sales also treat those units as unavailable and cannot force-sell a website reservation.

If an unpaid checkout expires, the reservation is released.

If a gateway or staff verifies full payment after the reservation has expired, StoreTrack retains the verified receipt/Finance movement but **does not create an intake silently**. The checkout becomes `paid_review`. Authorized staff can use the Commerce Payments queue to retry materialization. Recovery rechecks stock under locks and does not create a second charge.

A materialized stock checkout keeps its reservation until the intake is operationally accepted and the actual finished-stock sale is posted.

## Idempotency rules

Use a stable, unique `Idempotency-Key` for each logical operation:

- checkout creation: reuse the same key only when retrying the same checkout request;
- payment initialization: use a separate stable key per logical payment attempt;
- do not reuse an idempotency key for a different payment method or different basket.

StoreTrack enforces checkout/payment idempotency per tenant. Gateway events and verified receipts are also idempotent. Duplicate callbacks/retries cannot materialize a second intake for the same checkout.

## Legacy migration compatibility

The legacy endpoint remains operational:

```http
POST /api/v1/storefronts/{business_slug}/orders
```

It still creates `CommerceIntake` before payment so existing integrations do not break during deployment. Its response now includes:

```json
{
  "compatibility_mode": "legacy_intake_before_payment",
  "migration_endpoint": "/api/v1/storefronts/{business_slug}/checkouts"
}
```

New or upgraded websites should stop using `/orders` for initial submission and use `/checkouts` instead.

Existing intake-based payment endpoints remain available for historical/legacy orders:

```text
POST /orders/{order_uuid}/payments/initiate
GET  /orders/{order_uuid}/payments/current
POST /orders/{order_uuid}/payments/current/claim
```

No migration rewrites existing CommerceIntake, payment receipt, Sale, Production, or Finance history.

## Gateway webhook endpoints

Gateway webhooks continue to terminate directly at StoreTrack:

```text
POST /api/v1/storefronts/{business_slug}/payments/paystack/webhook
POST /api/v1/storefronts/{business_slug}/payments/monnify/webhook
```

The customer website must not proxy or forge these callbacks.

## Recommended website sequence

```text
GET products
  ↓
GET payment-methods
  ↓
POST checkouts  (Idempotency-Key A)
  ↓
POST checkouts/{id}/payments  (Idempotency-Key B)
  ↓
Gateway authorization OR transfer/cash instructions
  ↓
Poll checkout payment status
  ↓
verified full payment
  ↓
StoreTrack atomically creates exactly one CommerceIntake
  ↓
checkout response exposes order.id + order.number
  ↓
GET orders/{order.id} for downstream order/payment/fulfilment state
```
