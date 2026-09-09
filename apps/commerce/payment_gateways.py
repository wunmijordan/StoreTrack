"""Server-side gateway adapters for commerce payments.

The public commerce API receives no amount and never receives credentials.
Adapters initialize and verify transactions against tenant-owned configuration;
browser redirects are deliberately absent from the verification interface.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError

from .models import CommercePayment, CommercePaymentConfiguration


class GatewayError(ValidationError):
    pass


def _json_request(url, *, method="GET", headers=None, payload=None, timeout=30):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GatewayError(f"Payment provider returned HTTP {exc.code}: {detail[:240]}") from exc
    except URLError as exc:
        raise GatewayError(f"Could not reach payment provider: {exc.reason}") from exc
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise GatewayError("Payment provider returned an unreadable response.") from exc


def _require(value, message):
    if not value:
        raise GatewayError(message)
    return value


def _paystack_secret(config):
    return _require(config.paystack_secret_key, "Paystack is not fully configured for this business.")


def paystack_signature_valid(config, raw_body, signature):
    expected = hmac.new(_paystack_secret(config).encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)



def _payment_customer(payment):
    target = payment.checkout if payment.checkout_id else payment.intake
    if target is None:
        raise GatewayError("Payment is not attached to a checkout or order.")
    return target


def _payment_metadata(payment):
    return {
        "storetrack_payment_id": str(payment.public_id),
        "storetrack_checkout_id": str(payment.checkout.public_id) if payment.checkout_id else "",
        "storetrack_order_id": str(payment.intake.public_id) if payment.intake_id else "",
        "business_id": str(payment.business_id),
    }

def initialize_paystack(payment, config):
    target = _payment_customer(payment)
    email = _require(target.customer_email, "A customer email is required for Paystack checkout.")
    amount_minor = int((Decimal(payment.amount) * Decimal("100")).quantize(Decimal("1")))
    response = _json_request(
        "https://api.paystack.co/transaction/initialize",
        method="POST",
        headers={"Authorization": f"Bearer {_paystack_secret(config)}", "Content-Type": "application/json"},
        payload={
            "email": email,
            "amount": str(amount_minor),
            "currency": payment.currency,
            "reference": payment.reference,
            "callback_url": payment.return_url,
            "metadata": json.dumps(_payment_metadata(payment)),
        },
    )
    data = response.get("data") or {}
    if not response.get("status") or not data.get("authorization_url"):
        raise GatewayError(response.get("message") or "Paystack could not initialize the transaction.")
    return {
        "authorization_url": data["authorization_url"],
        "gateway_reference": data.get("reference") or payment.reference,
        "metadata": {"provider_status": response.get("status"), "access_code": data.get("access_code", "")},
    }


def verify_paystack(payment, config):
    response = _json_request(
        f"https://api.paystack.co/transaction/verify/{quote(payment.reference, safe='')}",
        headers={"Authorization": f"Bearer {_paystack_secret(config)}"},
    )
    data = response.get("data") or {}
    try:
        amount = Decimal(str(data.get("amount") or "0")) / Decimal("100")
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    metadata = data.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    verified = bool(
        response.get("status")
        and data.get("status") == "success"
        and str(data.get("reference") or "") == payment.reference
        and amount == Decimal(payment.amount)
        and str(data.get("currency") or "").upper() == payment.currency.upper()
        and str(metadata.get("storetrack_payment_id") or "") == str(payment.public_id)
        and str(metadata.get("storetrack_checkout_id") or "") == (str(payment.checkout.public_id) if payment.checkout_id else "")
        and str(metadata.get("storetrack_order_id") or "") == (str(payment.intake.public_id) if payment.intake_id else "")
        and str(metadata.get("business_id") or "") == str(payment.business_id)
    )
    return verified, {
        "status": data.get("status"),
        "reference": data.get("reference"),
        "gateway_reference": data.get("id"),
        "amount": str(amount),
        "currency": data.get("currency"),
        "paid_at": data.get("paid_at"),
    }


def _monnify_credentials(config):
    return (
        _require(config.monnify_api_key, "Monnify is not fully configured for this business."),
        _require(config.monnify_secret_key, "Monnify is not fully configured for this business."),
        _require(config.monnify_contract_code, "Monnify is not fully configured for this business."),
    )


def _monnify_token(config):
    api_key, secret_key, _ = _monnify_credentials(config)
    credentials = base64.b64encode(f"{api_key}:{secret_key}".encode("utf-8")).decode("ascii")
    response = _json_request(
        f"{config.monnify_base_url.rstrip('/')}/api/v1/auth/login",
        method="POST",
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
        payload={},
    )
    token = (response.get("responseBody") or {}).get("accessToken")
    if not response.get("requestSuccessful") or not token:
        raise GatewayError(response.get("responseMessage") or "Monnify authentication failed.")
    return token


def monnify_signature_valid(config, raw_body, signature):
    _, secret_key, _ = _monnify_credentials(config)
    # Monnify does not attach this header to sandbox notifications. Those
    # notifications still cannot settle funds until the transaction API
    # independently matches status, amount, currency, payment, order and tenant.
    if not signature and "sandbox.monnify.com" in config.monnify_base_url.lower():
        return True
    expected = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


def initialize_monnify(payment, config):
    target = _payment_customer(payment)
    email = _require(target.customer_email, "A customer email is required for Monnify checkout.")
    _, _, contract_code = _monnify_credentials(config)
    response = _json_request(
        f"{config.monnify_base_url.rstrip('/')}/api/v1/merchant/transactions/init-transaction",
        method="POST",
        headers={"Authorization": f"Bearer {_monnify_token(config)}", "Content-Type": "application/json"},
        payload={
            "amount": str(payment.amount),
            "customerName": target.customer_name,
            "customerEmail": email,
            "paymentReference": payment.reference,
            "paymentDescription": f"INPROFIC commerce {payment.reference}",
            "currencyCode": payment.currency,
            "contractCode": contract_code,
            "redirectUrl": payment.return_url,
            "paymentMethods": ["CARD", "ACCOUNT_TRANSFER", "USSD"],
            "metaData": {
                "storetrackPaymentId": str(payment.public_id),
                "storetrackCheckoutId": str(payment.checkout.public_id) if payment.checkout_id else "",
                "storetrackOrderId": str(payment.intake.public_id) if payment.intake_id else "",
                "businessId": str(payment.business_id),
            },
        },
    )
    body = response.get("responseBody") or {}
    if not response.get("requestSuccessful") or not body.get("checkoutUrl"):
        raise GatewayError(response.get("responseMessage") or "Monnify could not initialize the transaction.")
    return {
        "authorization_url": body["checkoutUrl"],
        "gateway_reference": body.get("transactionReference") or payment.reference,
        "metadata": {"provider_status": response.get("requestSuccessful")},
    }


def verify_monnify(payment, config):
    response = _json_request(
        f"{config.monnify_base_url.rstrip('/')}/api/v2/merchant/transactions/query?paymentReference={quote(payment.reference, safe='')}",
        headers={"Authorization": f"Bearer {_monnify_token(config)}"},
    )
    body = response.get("responseBody") or {}
    try:
        amount = Decimal(str(body.get("amountPaid") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    metadata = body.get("metaData") or body.get("metadata") or {}
    verified = bool(
        response.get("requestSuccessful")
        and body.get("paymentStatus") == "PAID"
        and str(body.get("paymentReference") or "") == payment.reference
        and amount == Decimal(payment.amount)
        and str(body.get("currencyCode") or body.get("currency") or "").upper() == payment.currency.upper()
        and str(metadata.get("storetrackPaymentId") or "") == str(payment.public_id)
        and str(metadata.get("storetrackCheckoutId") or "") == (str(payment.checkout.public_id) if payment.checkout_id else "")
        and str(metadata.get("storetrackOrderId") or "") == (str(payment.intake.public_id) if payment.intake_id else "")
        and str(metadata.get("businessId") or "") == str(payment.business_id)
    )
    return verified, {
        "status": body.get("paymentStatus"),
        "reference": body.get("paymentReference"),
        "gateway_reference": body.get("transactionReference"),
        "amount": str(amount),
        "currency": body.get("currencyCode") or body.get("currency"),
        "paid_at": body.get("paidOn") or body.get("completedOn"),
    }


def initialize_gateway(payment: CommercePayment, config: CommercePaymentConfiguration):
    if payment.method == CommercePayment.METHOD_PAYSTACK:
        return initialize_paystack(payment, config)
    if payment.method == CommercePayment.METHOD_MONNIFY:
        return initialize_monnify(payment, config)
    raise GatewayError("This payment does not use an online gateway.")


def verify_gateway(payment: CommercePayment, config: CommercePaymentConfiguration):
    if payment.method == CommercePayment.METHOD_PAYSTACK:
        return verify_paystack(payment, config)
    if payment.method == CommercePayment.METHOD_MONNIFY:
        return verify_monnify(payment, config)
    raise GatewayError("This payment does not use an online gateway.")
