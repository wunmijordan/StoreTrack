import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.services import is_business_admin
from core.models import Business
from core.verticals import vertical_config
from inventory.models import FinishedGood
from .forms import CommerceIntegrationForm, CommerceSettingsForm, StorefrontProductForm
from .models import CommerceCheckoutSession, CommerceIntegration, CommerceIntake, CommerceSettings, StorefrontProduct
from .services import ChannelMinimumError, accept_intake, create_intake, switch_intake_to_preorder
from .checkout_services import CheckoutAvailabilityError, available_physical_stock, create_checkout, serialize_checkout


def _settings_for(business):
    settings, _ = CommerceSettings.raw_objects.get_or_create(business=business, defaults={"created_by": None})
    return settings


def _commerce_enabled(business):
    from accounts.services import business_has_module
    return business_has_module(business, "commerce") and _settings_for(business).enabled


@login_required
def commerce_dashboard(request):
    settings = _settings_for(request.business)
    for good in FinishedGood.objects.all():
        StorefrontProduct.objects.get_or_create(
            finished_good=good,
            defaults={"business": request.business, "created_by": request.user, "allow_stock_order": True, "allow_preorder": request.business.uses_production},
        )
    products = FinishedGood.objects.select_related("storefront_product").order_by("name")
    intakes = CommerceIntake.objects.prefetch_related("items__finished_good", "payments")[:50]
    checkouts = CommerceCheckoutSession.objects.select_related("materialized_intake").prefetch_related("payments")[:50]
    integrations = CommerceIntegration.objects.all().order_by("name")
    return render(request, "commerce/dashboard.html", {"commerce_settings": settings, "products": products, "intakes": intakes, "checkouts": checkouts, "integrations": integrations if is_business_admin(request.user, request.business) else [], "can_manage_commerce": is_business_admin(request.user, request.business)})


@login_required
def commerce_settings(request):
    if not is_business_admin(request.user, request.business): return render(request, "403.html", status=403)
    obj = _settings_for(request.business)
    form = CommerceSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False); saved.business=request.business; saved.created_by = saved.created_by or request.user; saved.save()
        messages.success(request, "Commerce settings saved.")
        return redirect("commerce_dashboard")
    return render(request, "commerce/settings.html", {"form": form})


@login_required
def storefront_product_edit(request, good_id):
    if not is_business_admin(request.user, request.business): return render(request, "403.html", status=403)
    good = get_object_or_404(FinishedGood, pk=good_id)
    obj, _ = StorefrontProduct.objects.get_or_create(finished_good=good, defaults={"business": request.business, "created_by": request.user, "allow_preorder": request.business.uses_production})
    form = StorefrontProductForm(request.POST or None, request.FILES or None, instance=obj, business=request.business)
    if request.method == "POST" and form.is_valid():
        saved=form.save(commit=False); saved.business=request.business; saved.save()
        messages.success(request, f"Storefront settings saved for {good.name}.")
        return redirect("commerce_dashboard")
    return render(request, "commerce/product_form.html", {"form":form,"good":good})


@login_required
def integration_add(request):
    if not is_business_admin(request.user, request.business): return render(request, "403.html", status=403)
    settings = _settings_for(request.business)
    form=CommerceIntegrationForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        integration_type = form.cleaned_data["integration_type"]
        if integration_type == CommerceIntegration.TYPE_API and not settings.api_enabled:
            form.add_error("integration_type", "Enable Headless API in Commerce Settings first.")
        elif integration_type == CommerceIntegration.TYPE_WEBHOOK and not settings.connector_enabled:
            form.add_error("integration_type", "Enable Platform webhook / connector in Commerce Settings first.")
        else:
            obj=form.save(commit=False); obj.business=request.business; obj.created_by=request.user; obj.save()
            messages.success(request,"Integration credential created. Copy the credential now and keep it private.")
            return redirect("commerce_dashboard")
    return render(request,"commerce/integration_form.html",{"form":form})


@login_required
def intake_accept(request, public_id):
    intake=get_object_or_404(CommerceIntake, public_id=public_id)
    if request.method=="POST":
        try:
            accept_intake(intake,user=request.user); messages.success(request,f"{intake.public_number} processed using the business commerce policy.")
        except ValidationError as exc: messages.error(request,"; ".join(exc.messages))
    return redirect("commerce_dashboard")


def _public_catalog(request, business, settings, *, order_now_mode=False):
    products = StorefrontProduct.raw_objects.filter(
        business=business, published=True
    ).select_related("finished_good__business").prefetch_related("finished_good__channel_prices")
    return render(request, "commerce/storefront.html", {
        "store_business": business,
        "commerce_settings": settings,
        "products": products,
        "order_now_mode": order_now_mode,
        "commerce_channels": vertical_config(business)["commerce_channels"],
    })


def storefront(request,business_slug):
    business=get_object_or_404(Business,slug=business_slug)
    settings=_settings_for(business)
    if not _commerce_enabled(business) or not settings.hosted_storefront_enabled:
        return render(request,"404.html",status=404)
    return _public_catalog(request, business, settings)


def order_now(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    settings = _settings_for(business)
    if not _commerce_enabled(business) or not settings.order_now_link_enabled:
        return render(request, "404.html", status=404)
    return _public_catalog(request, business, settings, order_now_mode=True)


@require_http_methods(["POST"])
def storefront_order(request,business_slug):
    business=get_object_or_404(Business,slug=business_slug)
    settings = _settings_for(business)
    if not _commerce_enabled(business) or not (settings.hosted_storefront_enabled or settings.order_now_link_enabled):
        return render(request,"404.html",status=404)
    try:
        product=get_object_or_404(StorefrontProduct.raw_objects.select_related("finished_good"),business=business,public_id=request.POST.get("product_id"),published=True)
        intake,_=create_intake(business=business,source=CommerceIntake.SOURCE_STOREFRONT,sales_channel=request.POST.get("order_mode"),ordering_mode=request.POST.get("ordering_mode"),customer={"name":request.POST.get("customer_name"),"phone":request.POST.get("phone"),"email":request.POST.get("email"),"address":request.POST.get("address")},items=[{"storefront_product":product,"quantity":request.POST.get("quantity")}],service_mode=request.POST.get("service_mode",""),table_reference=request.POST.get("table_reference",""))
        return render(request,"commerce/storefront_success.html",{"store_business":business,"intake":intake})
    except (ValidationError,InvalidOperation,ValueError) as exc:
        return render(request,"commerce/storefront.html",{"store_business":business,"commerce_settings":_settings_for(business),"products":StorefrontProduct.raw_objects.filter(business=business,published=True).select_related("finished_good"),"commerce_channels":vertical_config(business)["commerce_channels"],"order_error":str(exc)},status=400)


def _api_business_and_auth(request,business_slug,write=False):
    business=get_object_or_404(Business,slug=business_slug)
    settings=_settings_for(business)
    if not _commerce_enabled(business) or not settings.api_enabled: return business,False
    if not write: return business,True
    key=request.headers.get("X-StoreTrack-Key","")
    return business,CommerceIntegration.raw_objects.filter(business=business,active=True,integration_type=CommerceIntegration.TYPE_API,api_key=key).exists()


def api_products(request,business_slug):
    business,ok=_api_business_and_auth(request,business_slug)
    if not ok:return JsonResponse({"detail":"Commerce API unavailable."},status=404)
    rows=[]
    channel_labels = vertical_config(business)["commerce_channels"]
    for p in StorefrontProduct.raw_objects.filter(business=business,published=True).select_related("finished_good__business").prefetch_related("finished_good__channel_prices"):
        order_modes=[]
        mode_config = [
            ("physical_store", p.allow_stock_order, p.min_quantity),
            ("online", p.allow_online_order, p.preorder_min_quantity),
            ("distribution", p.allow_distribution_order, p.distribution_min_quantity),
        ]
        for code, enabled, minimum in mode_config:
            if not enabled:
                continue
            fulfilment = "stock" if not business.uses_production or code == "physical_store" else "preorder"
            order_modes.append({
                "code": code,
                "label": channel_labels[code],
                "price": str(p.finished_good.selling_price_for(code)),
                "min_quantity": str(minimum),
                "max_quantity": str(p.max_quantity) if p.max_quantity is not None else None,
                "fulfilment_mode": fulfilment,
                "available_now": str(available_physical_stock(p.finished_good)) if fulfilment == "stock" else None,
                "lead_time": p.preorder_lead_time if fulfilment == "preorder" else "",
            })
        legacy_modes=[]
        if p.allow_stock_order:legacy_modes.append("order")
        if business.uses_production and (p.allow_online_order or p.allow_distribution_order):legacy_modes.append("preorder")
        image_url = p.public_image_url
        if image_url and image_url.startswith("/"):
            image_url = request.build_absolute_uri(image_url)
        rows.append({"id":str(p.public_id),"name":p.display_name,"description":p.description,"image_url":image_url,"unit":p.finished_good.unit,"available_now":str(available_physical_stock(p.finished_good)),"order_modes":order_modes,"ordering_modes":legacy_modes,"min_quantity":str(p.min_quantity),"preorder_min_quantity":str(p.preorder_min_quantity),"distribution_min_quantity":str(p.distribution_min_quantity),"max_quantity":str(p.max_quantity) if p.max_quantity is not None else None,"preorder_lead_time":p.preorder_lead_time,"stock_price":str(p.finished_good.selling_price_for("physical_store")),"preorder_price":str(p.finished_good.selling_price_for("online")),"distribution_price":str(p.finished_good.selling_price_for("distribution"))})
    return JsonResponse({"business":business.name,"service":business.get_vertical_display(),"products":rows})


@csrf_exempt
@require_http_methods(["POST"])
def api_checkouts(request, business_slug):
    business, ok = _api_business_and_auth(request, business_slug, write=True)
    if not ok:
        return JsonResponse({"detail": "Invalid or disabled commerce API credential."}, status=403)
    try:
        data = json.loads(request.body or b"{}")
        products = {
            str(p.public_id): p
            for p in StorefrontProduct.raw_objects.filter(
                business=business, published=True
            ).select_related("finished_good__business").prefetch_related("finished_good__channel_prices")
        }
        items = []
        for row in data.get("items") or []:
            product = products.get(str(row.get("product_id")))
            if not product:
                raise ValidationError("Unknown or unpublished product.")
            items.append({"storefront_product": product, "quantity": row.get("quantity")})
        checkout, created = create_checkout(
            business=business,
            source=CommerceIntake.SOURCE_API,
            order_mode=data.get("order_mode") or data.get("sales_channel"),
            ordering_mode=data.get("ordering_mode"),
            external_order_id=str(data.get("external_order_id") or ""),
            customer=data.get("customer") or {},
            service_mode=str(data.get("service_mode") or ""),
            table_reference=str(data.get("table_reference") or ""),
            items=items,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        payload = serialize_checkout(checkout)
        payload["created"] = created
        payload["payment_methods_url"] = f"/api/v1/storefronts/{business.slug}/payment-methods"
        payload["payment_url"] = f"/api/v1/storefronts/{business.slug}/checkouts/{checkout.public_id}/payments"
        return JsonResponse(payload, status=201 if created else 200)
    except ChannelMinimumError as exc:
        return JsonResponse({
            "detail": "; ".join(exc.messages),
            "code": "minimum_not_met",
            "suggested_order_modes": exc.alternatives,
        }, status=400)
    except CheckoutAvailabilityError as exc:
        return JsonResponse({
            "detail": "; ".join(exc.messages),
            "code": exc.code,
            "suggested_order_modes": exc.suggested_order_modes,
            "items": exc.details,
        }, status=409)
    except (json.JSONDecodeError, ValidationError, InvalidOperation, TypeError, ValueError) as exc:
        detail = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        return JsonResponse({"detail": detail}, status=400)


@require_http_methods(["GET"])
def api_checkout_detail(request, business_slug, checkout_id):
    business, ok = _api_business_and_auth(request, business_slug, write=True)
    if not ok:
        return JsonResponse({"detail": "Invalid or disabled commerce API credential."}, status=403)
    checkout = get_object_or_404(
        CommerceCheckoutSession.raw_objects.prefetch_related("items__storefront_product", "items__finished_good"),
        business=business,
        public_id=checkout_id,
    )
    return JsonResponse(serialize_checkout(checkout))


@csrf_exempt
@require_http_methods(["POST"])
def api_orders(request,business_slug):
    business,ok=_api_business_and_auth(request,business_slug,write=True)
    if not ok:return JsonResponse({"detail":"Invalid or disabled commerce API credential."},status=403)
    idem=request.headers.get("Idempotency-Key","").strip()
    if not idem:return JsonResponse({"detail":"Idempotency-Key header is required."},status=400)
    try:
        data=json.loads(request.body or b"{}")
        products={str(p.public_id):p for p in StorefrontProduct.raw_objects.filter(business=business,published=True).select_related("finished_good").prefetch_related("finished_good__channel_prices")}
        items=[]
        for row in data.get("items") or []:
            product=products.get(str(row.get("product_id")))
            if not product: raise ValidationError("Unknown or unpublished product.")
            items.append({"storefront_product":product,"quantity":row.get("quantity")})
        intake,created=create_intake(business=business,source=CommerceIntake.SOURCE_API,sales_channel=data.get("order_mode") or data.get("sales_channel"),ordering_mode=data.get("ordering_mode"),customer=data.get("customer") or {},items=items,idempotency_key=idem,external_order_id=str(data.get("external_order_id") or ""),service_mode=str(data.get("service_mode") or ""),table_reference=str(data.get("table_reference") or ""))
        return JsonResponse({"id":str(intake.public_id),"number":intake.public_number,"status":intake.status,"created":created,"order_mode":intake.sales_channel,"fulfilment_mode":intake.ordering_mode,"total":str(intake.total),"compatibility_mode":"legacy_intake_before_payment","migration_endpoint":f"/api/v1/storefronts/{business.slug}/checkouts"},status=201 if created else 200)
    except ChannelMinimumError as exc:
        return JsonResponse({"detail":"; ".join(exc.messages),"code":"minimum_not_met","suggested_order_modes":exc.alternatives},status=400)
    except (json.JSONDecodeError,ValidationError,InvalidOperation,TypeError,ValueError) as exc:
        detail="; ".join(exc.messages) if isinstance(exc,ValidationError) else str(exc)
        return JsonResponse({"detail":detail},status=400)


def api_order_detail(request,business_slug,public_id):
    business,ok=_api_business_and_auth(request,business_slug,write=True)
    if not ok:return JsonResponse({"detail":"Commerce API unavailable."},status=404)
    intake=get_object_or_404(CommerceIntake.raw_objects.prefetch_related("items__finished_good"),business=business,public_id=public_id)
    from .payment_services import current_payment, serialize_payment
    payment = current_payment(intake)
    compact_payment = None
    if payment:
        normalized = serialize_payment(payment)
        compact_payment = {
            key: normalized[key]
            for key in ("payment_id", "method", "status", "amount", "currency", "reference", "amount_paid", "balance", "verified_at")
        }
    return JsonResponse({"id":str(intake.public_id),"number":intake.public_number,"status":intake.status,"order_mode":intake.sales_channel,"fulfilment_mode":intake.ordering_mode,"ordering_mode":intake.ordering_mode,"payment_state":intake.payment_state,"payment":compact_payment,"fulfilment_state":intake.fulfilment_state,"total":str(intake.total),"items":[{"product":row.finished_good.name,"requested":str(row.requested_quantity),"stock_fulfilled":str(row.accepted_stock_quantity),"production":str(row.production_quantity),"price":str(row.unit_price)} for row in intake.items.all()]})


@require_http_methods(["POST"])
def storefront_switch_preorder(request, business_slug, public_id):
    business = get_object_or_404(Business, slug=business_slug)
    if not _commerce_enabled(business):
        return render(request, "404.html", status=404)
    intake = get_object_or_404(CommerceIntake.raw_objects, business=business, public_id=public_id)
    try:
        intake = switch_intake_to_preorder(intake, user=None)
        return render(request, "commerce/storefront_success.html", {"store_business": business, "intake": intake})
    except ValidationError as exc:
        return JsonResponse({"detail": "; ".join(exc.messages)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_order_switch_preorder(request, business_slug, public_id):
    business, ok = _api_business_and_auth(request, business_slug, write=True)
    if not ok:
        return JsonResponse({"detail": "Invalid or disabled commerce API credential."}, status=403)
    intake = get_object_or_404(CommerceIntake.raw_objects, business=business, public_id=public_id)
    try:
        switch_intake_to_preorder(intake, user=None)
        return JsonResponse({"id": str(intake.public_id), "status": "accepted", "order_mode": "online", "fulfilment_mode": "preorder", "ordering_mode": "preorder"})
    except ValidationError as exc:
        return JsonResponse({"detail": "; ".join(exc.messages)}, status=400)


def storefront_order_status(request, business_slug, public_id):
    business = get_object_or_404(Business, slug=business_slug)
    if not _commerce_enabled(business):
        return render(request, "404.html", status=404)
    intake = get_object_or_404(CommerceIntake.raw_objects.prefetch_related("items__finished_good"), business=business, public_id=public_id)
    return render(request, "commerce/storefront_status.html", {"store_business": business, "intake": intake})


@csrf_exempt
@require_http_methods(["POST"])
def connector_orders(request, business_slug, integration_id):
    """Receive a normalized third-party order event from a platform adapter/webhook.

    Unlike the headless API (used directly by a business-owned website), this
    endpoint is intended for push events from Shopify/WooCommerce/custom
    middleware. The connector signs the raw request body with its webhook secret.
    """
    business = get_object_or_404(Business, slug=business_slug)
    settings = _settings_for(business)
    if not _commerce_enabled(business) or not settings.connector_enabled:
        return JsonResponse({"detail": "Commerce connector unavailable."}, status=404)
    integration = get_object_or_404(
        CommerceIntegration.raw_objects,
        pk=integration_id, business=business, active=True, integration_type=CommerceIntegration.TYPE_WEBHOOK,
    )
    signature = request.headers.get("X-StoreTrack-Signature", "")
    expected = hmac.new(integration.webhook_secret.encode("utf-8"), request.body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        return JsonResponse({"detail": "Invalid connector signature."}, status=403)
    try:
        data = json.loads(request.body or b"{}")
        products = {str(p.public_id): p for p in StorefrontProduct.raw_objects.filter(business=business, published=True).select_related("finished_good").prefetch_related("finished_good__channel_prices")}
        items = []
        for row in data.get("items") or []:
            product = products.get(str(row.get("product_id")))
            if not product:
                raise ValidationError("Unknown or unpublished product.")
            items.append({"storefront_product": product, "quantity": row.get("quantity")})
        intake, created = create_intake(
            business=business, source=CommerceIntake.SOURCE_CONNECTOR,
            sales_channel=data.get("order_mode") or data.get("sales_channel"), ordering_mode=data.get("ordering_mode"), customer=data.get("customer") or {},
            items=items, external_order_id=str(data.get("external_order_id") or ""),
            idempotency_key=str(data.get("idempotency_key") or data.get("external_order_id") or ""),
            service_mode=str(data.get("service_mode") or ""), table_reference=str(data.get("table_reference") or ""),
        )
        return JsonResponse({"id": str(intake.public_id), "number": intake.public_number, "status": intake.status, "created": created, "order_mode": intake.sales_channel, "fulfilment_mode": intake.ordering_mode, "total": str(intake.total), "compatibility_mode": "legacy_connector_intake_before_payment"}, status=201 if created else 200)
    except ChannelMinimumError as exc:
        return JsonResponse({"detail": "; ".join(exc.messages), "code": "minimum_not_met", "suggested_order_modes": exc.alternatives}, status=400)
    except (json.JSONDecodeError, ValidationError, InvalidOperation, TypeError, ValueError) as exc:
        detail = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        return JsonResponse({"detail": detail}, status=400)
