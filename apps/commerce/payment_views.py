import hashlib
import json
from decimal import InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from accounts.services import is_business_admin, user_has_permission
from core.models import Business

from .forms import CommercePaymentConfigurationForm
from .models import (
    CommerceGatewayEvent,
    CommerceIntegration,
    CommerceIntake,
    CommercePayment,
    CommercePaymentClaim,
    CommercePaymentConfiguration,
    CommercePaymentReceipt,
)
from .payment_gateways import (
    GatewayError,
    monnify_signature_valid,
    paystack_signature_valid,
)
from .payment_services import (
    current_payment,
    initiate_payment,
    payment_configuration,
    process_gateway_event,
    record_verified_payment,
    reject_bank_claim,
    reverse_payment_receipt,
    serialize_payment,
    submit_bank_claim,
)
from .views import _commerce_enabled


def _error(exc):
    return "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)


def _headless_context(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    if not _commerce_enabled(business):
        return business, None
    key = request.headers.get("X-StoreTrack-Key", "")
    integration = CommerceIntegration.raw_objects.filter(
        business=business,
        active=True,
        integration_type=CommerceIntegration.TYPE_API,
        api_key=key,
    ).first()
    return business, integration


@csrf_exempt
@require_POST
def api_payment_initiate(request, business_slug, public_id):
    business, integration = _headless_context(request, business_slug)
    if integration is None:
        return JsonResponse({"detail": "Invalid or disabled commerce API credential."}, status=403)
    intake = get_object_or_404(
        CommerceIntake.raw_objects.prefetch_related("items"), business=business, public_id=public_id
    )
    try:
        data = json.loads(request.body or b"{}")
        payment = initiate_payment(
            intake=intake,
            method=data.get("method"),
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            return_url=data.get("return_url", ""),
        )
        return JsonResponse(serialize_payment(payment), status=200)
    except (json.JSONDecodeError, ValidationError, GatewayError, TypeError, ValueError) as exc:
        return JsonResponse({"detail": _error(exc)}, status=400)


@require_http_methods(["GET"])
def api_payment_current(request, business_slug, public_id):
    business, integration = _headless_context(request, business_slug)
    if integration is None:
        return JsonResponse({"detail": "Invalid or disabled commerce API credential."}, status=403)
    intake = get_object_or_404(CommerceIntake.raw_objects, business=business, public_id=public_id)
    payment = current_payment(intake)
    if payment is None:
        return JsonResponse({"detail": "No payment has been initiated for this order."}, status=404)
    return JsonResponse(serialize_payment(payment))


@csrf_exempt
@require_POST
def api_payment_claim(request, business_slug, public_id):
    business, integration = _headless_context(request, business_slug)
    if integration is None:
        return JsonResponse({"detail": "Invalid or disabled commerce API credential."}, status=403)
    intake = get_object_or_404(CommerceIntake.raw_objects, business=business, public_id=public_id)
    payment = current_payment(intake)
    if payment is None:
        return JsonResponse({"detail": "No current payment exists for this order."}, status=404)
    try:
        data = json.loads(request.body or b"{}")
        claim, created = submit_bank_claim(
            payment=payment,
            payer_name=data.get("payer_name"),
            transfer_reference=data.get("transfer_reference"),
        )
        payment.refresh_from_db()
        payload = serialize_payment(payment)
        payload["claim_created"] = created
        return JsonResponse(payload, status=201 if created else 200)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        return JsonResponse({"detail": _error(exc)}, status=400)


def _safe_gateway_payload(value):
    blocked = {"authorization", "authorization_code", "card", "token", "secret", "api_key"}
    if isinstance(value, dict):
        return {
            str(key): _safe_gateway_payload(item)
            for key, item in value.items()
            if str(key).lower() not in blocked
        }
    if isinstance(value, list):
        return [_safe_gateway_payload(item) for item in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _gateway_reference(provider, payload):
    if provider == CommercePayment.METHOD_PAYSTACK:
        data = payload.get("data") or {}
        return str(data.get("reference") or ""), str(payload.get("event") or "")
    data = payload.get("eventData") or payload.get("event_data") or {}
    return str(data.get("paymentReference") or data.get("payment_reference") or ""), str(payload.get("eventType") or payload.get("event_type") or "")


@csrf_exempt
@require_POST
def gateway_webhook(request, business_slug, provider):
    if provider not in {CommercePayment.METHOD_PAYSTACK, CommercePayment.METHOD_MONNIFY}:
        return JsonResponse({"detail": "Unknown payment provider."}, status=404)
    business = get_object_or_404(Business, slug=business_slug)
    config = CommercePaymentConfiguration.raw_objects.filter(business=business).first()
    if config is None:
        return JsonResponse({"detail": "Payment provider is not configured."}, status=404)
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)
    reference, event_type = _gateway_reference(provider, payload)
    payment = CommercePayment.raw_objects.filter(
        Q(reference=reference) | Q(gateway_reference=reference),
        business=business,
        method=provider,
    ).select_related("intake").first()
    signature = (
        request.headers.get("x-paystack-signature", "")
        if provider == CommercePayment.METHOD_PAYSTACK
        else request.headers.get("monnify-signature", "")
    )
    try:
        signature_valid = (
            paystack_signature_valid(config, request.body, signature)
            if provider == CommercePayment.METHOD_PAYSTACK
            else monnify_signature_valid(config, request.body, signature)
        )
    except (ValidationError, GatewayError):
        signature_valid = False
    event_key = hashlib.sha256(
        provider.encode("utf-8") + b":" + signature.encode("utf-8") + b":" + request.body
    ).hexdigest()
    event, created = CommerceGatewayEvent.raw_objects.get_or_create(
        business=business,
        provider=provider,
        event_key=event_key,
        defaults={
            "payment": payment,
            "event_type": event_type,
            "signature_valid": signature_valid,
            "payload": _safe_gateway_payload(payload),
            "error": "" if payment else "No tenant-owned payment matched the provider reference.",
        },
    )
    if not signature_valid:
        if created:
            event.error = "Invalid webhook signature."
            event.processed_at = timezone.now()
            event.save(update_fields=["error", "processed_at", "updated_at"])
        return JsonResponse({"detail": "Invalid webhook signature."}, status=403)
    if not created and event.processed_at:
        return JsonResponse({"received": True, "duplicate": True})
    if payment is None:
        if created:
            event.processed_at = timezone.now()
            event.save(update_fields=["processed_at", "updated_at"])
        return JsonResponse({"detail": "Unknown payment reference."}, status=400)
    try:
        event = process_gateway_event(event=event)
    except (ValidationError, GatewayError, TypeError, ValueError) as exc:
        event.error = _error(exc)[:500]
        event.save(update_fields=["error", "updated_at"])
        return JsonResponse({"detail": "Provider verification could not be completed."}, status=400)
    if not event.provider_verified:
        return JsonResponse({"detail": "Provider verification did not match this payment."}, status=400)
    return JsonResponse({"received": True, "duplicate": not created})


def _can_verify(user, business):
    return is_business_admin(user, business) or user_has_permission(user, business, "finance", "edit")


@login_required
def payment_settings(request):
    if not is_business_admin(request.user, request.business):
        return render(request, "403.html", status=403)
    config = payment_configuration(request.business)
    form = CommercePaymentConfigurationForm(
        request.POST or None, instance=config, business=request.business
    )
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.business = request.business
        saved.created_by = saved.created_by or request.user
        saved.save()
        messages.success(request, "Commerce payment settings saved. Credentials remain server-side.")
        return redirect("commerce_payment_settings")
    return render(request, "commerce/payment_settings.html", {"form": form, "config": config})


@login_required
def payment_queue(request):
    if not user_has_permission(request.user, request.business, "finance", "view") and not is_business_admin(request.user, request.business):
        return render(request, "403.html", status=403)
    payments = list(CommercePayment.objects.select_related(
        "intake", "verified_by"
    ).prefetch_related(
        "claims__reviewed_by", "receipts__verified_by", "receipts__reversed_by",
        "gateway_events",
    )[:100])
    for payment in payments:
        payment.confirmation_token = f"{payment.public_id}:{payment.updated_at.isoformat()}"
    return render(request, "commerce/payments.html", {
        "payments": payments,
        "can_verify": _can_verify(request.user, request.business),
        "can_manage_payment_settings": is_business_admin(request.user, request.business),
    })


@login_required
@require_POST
def payment_confirm(request, public_id):
    if not _can_verify(request.user, request.business):
        return render(request, "403.html", status=403)
    payment = get_object_or_404(CommercePayment, business=request.business, public_id=public_id)
    try:
        claim = None
        claim_id = request.POST.get("claim_id")
        if claim_id:
            claim = get_object_or_404(
                CommercePaymentClaim, business=request.business, payment=payment, pk=claim_id
            )
        token = (request.POST.get("confirmation_token") or "").strip()
        if not token:
            raise ValidationError("The confirmation token is missing; reload and try again.")
        receipt, created = record_verified_payment(
            payment=payment,
            amount=request.POST.get("amount"),
            actor=request.user,
            idempotency_key=f"manual:{token}",
            external_reference=request.POST.get("external_reference", ""),
            note=request.POST.get("note", ""),
            location=request.POST.get("location", ""),
            claim=claim,
        )
        messages.success(request, "Payment confirmed." if created else "That confirmation was already recorded.")
    except (ValidationError, InvalidOperation, TypeError, ValueError) as exc:
        messages.error(request, _error(exc))
    return redirect("commerce_payment_queue")


@login_required
@require_POST
def payment_claim_reject(request, claim_id):
    if not _can_verify(request.user, request.business):
        return render(request, "403.html", status=403)
    claim = get_object_or_404(CommercePaymentClaim, business=request.business, pk=claim_id)
    try:
        reject_bank_claim(claim=claim, actor=request.user, reason=request.POST.get("reason"))
        messages.success(request, "Transfer claim rejected; its audit history was retained.")
    except ValidationError as exc:
        messages.error(request, _error(exc))
    return redirect("commerce_payment_queue")


@login_required
@require_POST
def payment_reconcile(request, public_id):
    if not _can_verify(request.user, request.business):
        return render(request, "403.html", status=403)
    payment = get_object_or_404(
        CommercePayment, business=request.business, public_id=public_id,
        method__in=[CommercePayment.METHOD_PAYSTACK, CommercePayment.METHOD_MONNIFY],
    )
    event = CommerceGatewayEvent.raw_objects.create(
        business=request.business,
        created_by=request.user,
        payment=payment,
        provider=payment.method,
        event_key=f"manual-reconcile:{payment.public_id}:{timezone.now().timestamp()}",
        event_type="manual_reconcile",
        signature_valid=True,
        payload={"requested_by_user_id": request.user.pk},
    )
    try:
        event = process_gateway_event(event=event)
        if event.provider_verified:
            messages.success(request, "Provider verification completed and the payment is reconciled.")
        else:
            messages.error(request, "The provider response did not match the expected payment.")
    except (ValidationError, GatewayError, TypeError, ValueError) as exc:
        event.error = _error(exc)[:500]
        event.save(update_fields=["error", "updated_at"])
        messages.error(request, "Provider reconciliation could not be completed.")
    return redirect("commerce_payment_queue")


@login_required
@require_POST
def payment_receipt_reverse(request, receipt_id):
    if not _can_verify(request.user, request.business):
        return render(request, "403.html", status=403)
    receipt = get_object_or_404(CommercePaymentReceipt, business=request.business, pk=receipt_id)
    try:
        receipt, created = reverse_payment_receipt(
            receipt=receipt, actor=request.user, reason=request.POST.get("reason")
        )
        messages.success(request, "Receipt reversed with compensating finance entries." if created else "Receipt was already reversed.")
    except ValidationError as exc:
        messages.error(request, _error(exc))
    return redirect("commerce_payment_queue")
