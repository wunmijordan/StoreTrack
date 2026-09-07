# Prompt for the StoreTrack agent — headless commerce payments

Implement the StoreTrack side of payments for the existing headless commerce integration used by the No Left Overs Nigeria restaurant website. Preserve StoreTrack as the source of truth for order totals, payment state, receivables/finance, and fulfilment. Do not move payment authority into the storefront.

## Existing storefront contract

The NLO website already creates commerce orders through the existing authenticated headless endpoint and expects the order's StoreTrack-generated `public_id` and authoritative `total`. It now supports four payment methods:

- `paystack`
- `monnify`
- `bank_transfer`
- `cash`

The website intentionally never sends an amount when initiating payment. StoreTrack must derive the payable amount from the order and its own pricing/finance state.

Implement these authenticated headless endpoints under the same storefront/business slug and `X-StoreTrack-Key` authentication used by the current commerce API:

### 1. Initiate/select payment

`POST /api/v1/storefronts/{business_slug}/orders/{public_id}/payments/initiate`

Request:

```json
{
  "method": "paystack|monnify|bank_transfer|cash",
  "return_url": "https://storefront.example/order/<uuid>/payment/return/"
}
```

Requirements:

- Require/obey `Idempotency-Key` so retries never create duplicate payment attempts or duplicate finance entries.
- Resolve the order by tenant/business and public ID only.
- Derive amount/currency from StoreTrack. Never trust an amount from the storefront even if one is supplied.
- Refuse payment attempts for cancelled/voided orders and enforce any existing order/payment eligibility rules.
- Reuse an active compatible attempt when idempotency or current-state rules require it.
- Return a normalized response shape, e.g.:

```json
{
  "payment_id": "uuid",
  "method": "paystack",
  "status": "pending",
  "amount": "1200.00",
  "currency": "NGN",
  "reference": "STP-...",
  "authorization_url": "https://...",
  "instructions": "",
  "bank_account": null,
  "expires_at": null
}
```

For bank transfer, return the configured business account in:

```json
{
  "bank_account": {
    "bank_name": "...",
    "account_name": "...",
    "account_number": "..."
  },
  "instructions": "Use the order/payment reference when transferring."
}
```

For cash, return a pending/manual-verification status and clear customer instructions. Do not mark cash paid at initiation.

### 2. Current payment

`GET /api/v1/storefronts/{business_slug}/orders/{public_id}/payments/current`

Return the normalized current payment record, including at least method, status, amount, currency, StoreTrack payment reference, gateway reference when applicable, bank account/instructions when appropriate, `amount_paid`, `balance`, and verification timestamps if available.

Also enrich the existing order-status payload with a compact `payment` object while preserving existing `payment_state` compatibility.

### 3. Bank transfer claim from storefront

`POST /api/v1/storefronts/{business_slug}/orders/{public_id}/payments/current/claim`

Request:

```json
{
  "payer_name": "Ada Example",
  "transfer_reference": "bank/session/reference"
}
```

This is a **claim/evidence submission, not verification**. It must move the payment only to something like `awaiting_verification`. It must never set `paid` merely because the customer supplied a reference.

Make transfer references appropriately unique/deduplicated where possible and audit every claim. If you support proof uploads elsewhere in StoreTrack, link them to the payment attempt, but do not require the headless website to determine validity.

## Paystack

Implement Paystack as a proper server-side gateway integration:

- Store Paystack secret keys only in StoreTrack business/integration settings; never expose them through the headless API.
- Initialize the transaction server-side with the StoreTrack authoritative amount converted to kobo, NGN currency, customer email when available, and StoreTrack payment/order references in metadata.
- Return only the gateway authorization URL/reference needed by the storefront.
- Add a Paystack webhook endpoint in StoreTrack and verify the Paystack signature (`x-paystack-signature`) against the raw request body using the business/integration secret.
- Treat the browser return/callback as navigation only, never proof of payment.
- On webhook success, independently verify/reference-check the transaction against Paystack as appropriate before mutating accounting state.
- Validate reference, expected amount, currency, business/order/payment ownership, and that the event is not a replay.
- Make webhook processing idempotent. Duplicate events must not duplicate payments, receipts, ledger entries, Sale records, or stock/production actions.
- Persist gateway event IDs/references and enough raw metadata for audit without storing sensitive card data.

## Monnify

Implement Monnify with the same trust boundary:

- Keep API/secret/contract credentials only in StoreTrack configuration.
- Initialize transactions server-side from the StoreTrack amount and return the checkout/payment URL/reference.
- Implement Monnify webhook/transaction-notification verification according to Monnify's current signature/hash requirements.
- Do not trust the storefront redirect.
- Verify reference, amount, currency, tenant/business ownership and payment attempt before marking paid.
- Make webhook processing idempotent and auditable.
- Do not duplicate finance or commerce effects on repeated webhook delivery.

Use provider adapter/service classes rather than embedding gateway-specific logic throughout commerce views. The normalized payment model/API should allow additional providers later.

## Bank transfer verification

Bank transfer has no gateway confirmation in this flow, so implement explicit StoreTrack-controlled verification:

- Customer-submitted transfer reference -> `awaiting_verification`, never `paid`.
- Provide an internal StoreTrack UI/action for authorized finance/business staff to review the claim against bank evidence/statement/actual credit.
- Verification must capture verifier user, timestamp, confirmed amount, bank/reference, optional note/evidence, and any mismatch reason.
- If confirmed amount is below amount due, use StoreTrack's existing partial-payment/receivable semantics rather than pretending it is fully paid.
- Prevent the same external transfer reference from being used to pay multiple orders unless an explicit, audited allocation workflow supports it.
- Rejection should retain the audit trail and allow a corrected/new claim without deleting history.
- Only successful staff verification should post the finance receipt/clear the receivable and advance the canonical payment state.

If StoreTrack already has bank-transaction reconciliation functionality, integrate with it rather than creating a parallel accounting system.

## Cash verification

Cash must also be manually verified in StoreTrack:

- Selecting cash creates a pending cash payment intent only.
- Payment becomes received/paid only when an authorized staff member confirms physical receipt.
- Confirmation must capture receiver user, timestamp, amount actually received, location/outlet if StoreTrack models one, and optional note.
- Support partial cash amounts using existing partial-payment logic.
- Reversal/correction must be permission-controlled and audited; never silently edit the original receipt.
- Customer/storefront cannot call an endpoint that self-confirms cash.

## Canonical states and finance behavior

Use or adapt StoreTrack's existing payment/receivable models instead of building duplicate accounting. At minimum distinguish:

- `pending`
- `awaiting_customer`
- `awaiting_verification`
- `paid` / `partially_paid`
- `failed`
- `cancelled`
- `refunded` where existing StoreTrack finance supports it

Keep order status, payment status and fulfilment status independent. A paid order is not automatically fulfilled; a fulfilled/cash order is not automatically paid until cash is verified.

When a payment is verified/settled:

- update the canonical payment record;
- update amount paid/balance;
- clear or reduce the correct receivable;
- create exactly one appropriate finance/receipt/ledger effect using existing StoreTrack mechanisms;
- preserve commerce intake/order linkage;
- do not create duplicate Sale or ProductionOrder objects if the existing commerce workflow already creates them at another lifecycle stage.

## Security, permissions and audit

- Keep all secrets server-side.
- Headless endpoints must be tenant-scoped and authenticated with the existing StoreTrack headless credential rules.
- Internal bank/cash verification requires explicit staff permissions; API key possession alone must not allow manual payment verification.
- Use constant-time/signature-safe verification where applicable.
- Validate callback/webhook payloads defensively.
- Store audit records for gateway callbacks, manual verification, reversals and status changes.
- Never log API secrets or full sensitive payment credentials.

## StoreTrack admin/business UI

Add a practical payment area to the relevant commerce/order/finance screens showing:

- method/provider;
- payment reference;
- gateway/external reference;
- amount due, paid and balance;
- verification state;
- payer/claim data for bank transfer;
- verifier/receiver and timestamps for manual methods;
- retry/reconcile/reject/confirm actions according to permission and state;
- audit history.

Bank and cash confirmations need clear warning/confirmation guards because they create financial truth without a gateway.

## Tests

Add tests covering at least:

1. storefront cannot choose/alter the payable amount;
2. payment initialization is tenant-scoped and idempotent;
3. Paystack webhook signature/reference/amount validation and replay safety;
4. Monnify notification signature/reference/amount validation and replay safety;
5. browser return URL alone never marks payment paid;
6. customer bank claim only becomes `awaiting_verification`;
7. only authorized StoreTrack staff can verify bank transfer/cash;
8. manual verification records actor/time/amount and updates receivable once;
9. partial payments preserve balance correctly;
10. duplicate gateway/manual submissions do not duplicate finance entries;
11. order/payment/fulfilment states remain independent;
12. existing headless order/catalogue behavior remains backward compatible.

Before finishing, run migrations/tests/checks and provide the usual exact outline of every modified, added and removed file.
