from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Business
from .models import (
    BusinessFeatureAccess,
    BusinessModuleAccess,
    BusinessSubscription,
    RoleModulePermission,
    SubscriptionPayment,
    SubscriptionPlan,
    SubscriptionPlanModule,
    SubscriptionPromotion,
    SubscriptionService,
    UserBusiness,
)
from .services import ensure_permissions, invalidate_business_access_cache, seed_business_roles


PLAN_MATRIX = {
    SubscriptionPlan.CODE_STARTER: {
        "dashboard": "full", "inventory": "full", "sales": "full", "expenses": "full",
        "procurement": "none", "production": "none", "finance": "none", "reports": "basic",
        "users": "full", "commerce": "none",
    },
    SubscriptionPlan.CODE_PRODUCTION: {
        "dashboard": "full", "inventory": "full", "procurement": "full", "production": "full",
        "sales": "full", "expenses": "full", "finance": "none", "reports": "full",
        "users": "full", "commerce": "none",
    },
    SubscriptionPlan.CODE_BUSINESS_PRO: {module: "full" for module, _ in RoleModulePermission.MODULE_CHOICES},
}


def ensure_default_plans():
    """Ensure built-in plans and entitlement rows exist with bounded queries.

    The previous implementation performed get/update-or-create work for every
    plan/module pair on every page visit. This version keeps the same
    self-healing semantics, but reads the complete seed state in two queries
    and only writes when something is actually missing or has drifted.
    """
    names = {
        SubscriptionPlan.CODE_STARTER: "STARTER",
        SubscriptionPlan.CODE_PRODUCTION: "PRODUCTION",
        SubscriptionPlan.CODE_BUSINESS_PRO: "BUSINESS PRO",
    }
    codes = tuple(names)

    plan_rows = list(SubscriptionPlan.objects.filter(code__in=codes))
    plans = {plan.code: plan for plan in plan_rows}
    missing_codes = [code for code in codes if code not in plans]
    if missing_codes:
        # Creation is exceptional, so retain get-or-create's strict conflict
        # behavior without paying its per-plan cost on ordinary page loads.
        with transaction.atomic():
            for code in missing_codes:
                plan, _created = SubscriptionPlan.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": names[code], "trial_days": 30,
                        "monthly_price": Decimal("0.00"),
                    },
                )
                plans[code] = plan

    # Preserve founder-configured names/pricing. The historical invariant was
    # only that the built-in trial length remains 30 days.
    trial_updates = []
    for plan in plans.values():
        if plan.trial_days != 30:
            plan.trial_days = 30
            trial_updates.append(plan)
    entitlement_rows = list(
        SubscriptionPlanModule.objects.filter(plan_id__in=[plan.pk for plan in plans.values()])
    )
    entitlements = {(row.plan_id, row.module): row for row in entitlement_rows}
    missing_entitlements = []
    entitlement_updates = []
    for code in codes:
        plan = plans.get(code)
        if not plan:
            continue
        for module, _label in RoleModulePermission.MODULE_CHOICES:
            level = PLAN_MATRIX[code].get(module, "none")
            enabled = level != "none"
            row = entitlements.get((plan.pk, module))
            if row is None:
                missing_entitlements.append(
                    SubscriptionPlanModule(
                        plan=plan, module=module, enabled=enabled, level=level,
                    )
                )
                continue
            if row.enabled != enabled or row.level != level:
                row.enabled = enabled
                row.level = level
                entitlement_updates.append(row)

    if trial_updates or missing_entitlements or entitlement_updates:
        with transaction.atomic():
            if trial_updates:
                SubscriptionPlan.objects.bulk_update(trial_updates, ["trial_days"])
            if missing_entitlements:
                SubscriptionPlanModule.objects.bulk_create(missing_entitlements, ignore_conflicts=True)
            if entitlement_updates:
                SubscriptionPlanModule.objects.bulk_update(entitlement_updates, ["enabled", "level"])

    return plans


def business_has_feature(business, feature):
    if not business:
        return False
    from core.context import get_request_cache

    cache = get_request_cache()
    key = ("business_feature_access", business.pk)
    if cache is not None and key in cache:
        feature_access = cache[key]
    else:
        feature_access = dict(
            BusinessFeatureAccess.objects.filter(business=business).values_list("feature", "enabled")
        )
        if cache is not None:
            cache[key] = feature_access
    row = feature_access.get(feature)
    # Missing feature rows retain legacy/full behavior until a subscription is explicitly applied.
    return row is not False


@transaction.atomic
def apply_subscription_entitlements(subscription):
    """Make BusinessModuleAccess the hard entitlement boundary for every service profile."""
    subscription = BusinessSubscription.objects.select_related("plan").get(pk=subscription.pk)
    plan_rows = {
        row.module: row
        for row in subscription.plan.module_entitlements.all()
    }
    source = BusinessModuleAccess.SOURCE_FOUNDER if subscription.founder_lifetime else BusinessModuleAccess.SOURCE_PLAN
    active = subscription.is_effectively_active
    for service in subscription.services.select_related("business"):
        business = service.business
        for module, _label in RoleModulePermission.MODULE_CHOICES:
            entitlement = plan_rows.get(module)
            enabled = bool((active and entitlement and entitlement.enabled) or (not active and module == "dashboard"))
            # Preserve vertical/service capability restrictions in the central permission resolver;
            # this row represents commercial entitlement only.
            BusinessModuleAccess.objects.update_or_create(
                business=business,
                module=module,
                defaults={"enabled": enabled, "source": source},
            )
        reports = plan_rows.get("reports")
        BusinessFeatureAccess.objects.update_or_create(
            business=business,
            feature="reports_full",
            defaults={"enabled": bool(active and reports and reports.enabled and reports.level == "full"), "source": source},
        )
        invalidate_business_access_cache(business)
    return subscription


@transaction.atomic
def start_trial_for_business(business, plan=None):
    plans = ensure_default_plans()
    plan = plan or plans[SubscriptionPlan.CODE_STARTER]
    now = timezone.now()
    subscription, created = BusinessSubscription.objects.get_or_create(
        primary_business=business,
        defaults={
            "plan": plan,
            "status": BusinessSubscription.STATUS_TRIAL,
            "trial_ends_at": now + timezone.timedelta(days=30),
        },
    )
    if created:
        SubscriptionService.objects.create(subscription=subscription, business=business, is_primary=True)
        apply_subscription_entitlements(subscription)
    return subscription


@transaction.atomic
def switch_subscription_plan(subscription, plan, *, keep_expiry=True):
    subscription.plan = plan
    if not keep_expiry and not subscription.founder_lifetime:
        subscription.status = BusinessSubscription.STATUS_ACTIVE
        subscription.paid_until = timezone.now() + timezone.timedelta(days=30)
    subscription.save()
    return apply_subscription_entitlements(subscription)


@transaction.atomic
def grant_founder_lifetime(subscription, plan, actor, note=""):
    subscription.plan = plan
    subscription.status = BusinessSubscription.STATUS_FOUNDER
    subscription.founder_lifetime = True
    subscription.founder_granted_by = actor
    subscription.founder_granted_at = timezone.now()
    subscription.founder_note = note
    subscription.trial_ends_at = None
    subscription.paid_until = None
    subscription.save()
    return apply_subscription_entitlements(subscription)


@transaction.atomic
def revoke_founder_lifetime(subscription):
    subscription.founder_lifetime = False
    subscription.founder_granted_by = None
    subscription.founder_granted_at = None
    subscription.status = BusinessSubscription.STATUS_EXPIRED
    subscription.save()
    return apply_subscription_entitlements(subscription)


@transaction.atomic
def add_service_business(subscription, *, name, service_type, actor):
    """Provision a separate Business profile under the same commercial subscription."""
    from django.utils.text import slugify
    base = (slugify(name) or "business")[:52]
    slug = base
    suffix = 2
    while Business.objects.filter(slug=slug).exists():
        token = f"-{suffix}"
        slug = f"{base[:60-len(token)]}{token}"
        suffix += 1
    business = Business.objects.create(
        name=name.strip(), slug=slug, vertical=service_type,
        accent_color=subscription.primary_business.accent_color,
        background_color=subscription.primary_business.background_color,
        currency_symbol=subscription.primary_business.currency_symbol,
    )
    roles = seed_business_roles(business)
    SubscriptionService.objects.create(subscription=subscription, business=business, is_primary=False)
    # Give every active member of the primary profile the same system-role key where possible.
    for membership in UserBusiness.objects.filter(business=subscription.primary_business, active=True).select_related("user", "role"):
        role = roles.get(membership.role.key) or roles.get("stock_keeper")
        new_membership, _ = UserBusiness.objects.get_or_create(
            user=membership.user, business=business, defaults={"role": role, "active": True}
        )
        ensure_permissions(new_membership)
    apply_subscription_entitlements(subscription)
    return business


def active_promotion_for_plan(plan, *, moment=None):
    """Resolve at most one effective promotion for a plan without changing its base price."""
    moment = moment or timezone.now()
    prefetched = getattr(plan, "_active_promotions", None)
    if prefetched is not None:
        candidates = [promo for promo in prefetched if promo.active and promo.starts_at <= moment < promo.ends_at]
        return sorted(candidates, key=lambda promo: (promo.starts_at, promo.pk or 0), reverse=True)[0] if candidates else None
    return (
        SubscriptionPromotion.objects.filter(
            plan=plan, active=True, starts_at__lte=moment, ends_at__gt=moment
        )
        .order_by("-starts_at", "-id")
        .first()
    )


def attach_active_promotions(plans, *, moment=None):
    """Attach active promotions to an already-loaded plan collection in one query."""
    moment = moment or timezone.now()
    plans = list(plans)
    plan_ids = [plan.pk for plan in plans]
    rows = SubscriptionPromotion.objects.filter(
        plan_id__in=plan_ids, active=True, starts_at__lte=moment, ends_at__gt=moment
    ).order_by("plan_id", "-starts_at", "-id")
    by_plan = {}
    for promo in rows:
        by_plan.setdefault(promo.plan_id, []).append(promo)
    for plan in plans:
        plan._active_promotions = by_plan.get(plan.pk, [])
        plan.current_promotion = plan._active_promotions[0] if plan._active_promotions else None
    return plans


def effective_monthly_price(plan, promotion=None):
    if promotion is False:
        return Decimal(plan.monthly_price or 0).quantize(Decimal("0.01"))
    promotion = promotion if promotion is not None else active_promotion_for_plan(plan)
    return promotion.discounted_monthly_price if promotion else Decimal(plan.monthly_price or 0).quantize(Decimal("0.01"))


def effective_additional_service_monthly_price(plan, promotion=None):
    if promotion is False:
        return plan.additional_service_monthly_price
    promotion = promotion if promotion is not None else active_promotion_for_plan(plan)
    if promotion:
        return promotion.discounted_additional_service_monthly_price
    return plan.additional_service_monthly_price


def payment_amount(plan, service_count, months=1, billing_cycle="monthly", promotion=None):
    service_count = max(1, int(service_count or 1))
    if promotion is None:
        promotion = active_promotion_for_plan(plan)
    base_monthly = effective_monthly_price(plan, promotion)
    addon_monthly = effective_additional_service_monthly_price(plan, promotion)
    monthly_total = base_monthly + Decimal(service_count - 1) * addon_monthly
    if billing_cycle == SubscriptionPayment.CYCLE_YEARLY:
        discount = min(max(plan.yearly_discount_percent, Decimal("0")), Decimal("100"))
        return (monthly_total * Decimal("12") * (Decimal("1") - discount / Decimal("100"))).quantize(Decimal("0.01"))
    months = max(1, int(months or 1))
    return (monthly_total * Decimal(months)).quantize(Decimal("0.01"))


def payment_is_locked(subscription, plan):
    """Prevent premature renewal of the plan already providing active access."""
    if not subscription or not subscription.is_effectively_active or subscription.plan_id != plan.pk:
        return False
    return subscription.founder_lifetime or not subscription.is_expiring_soon


@transaction.atomic
def create_payment_request(subscription, plan, *, months=1, billing_cycle="monthly", provider="manual"):
    if payment_is_locked(subscription, plan):
        if subscription.founder_lifetime:
            raise ValidationError("Your current plan has founder lifetime access and does not require payment.")
        raise ValidationError("Renewal for your current plan opens within 7 days of its expiry date.")
    if billing_cycle == SubscriptionPayment.CYCLE_YEARLY:
        months = 12
    service_count = max(1, subscription.services.count())
    promotion = active_promotion_for_plan(plan)
    base_amount = payment_amount(plan, service_count, months, billing_cycle=billing_cycle, promotion=False)
    amount = payment_amount(plan, service_count, months, billing_cycle=billing_cycle, promotion=promotion)
    if amount <= 0:
        raise ValidationError("This plan does not yet have a payable price configured. Contact the INPROFIC founder/superuser.")
    return SubscriptionPayment.objects.create(
        subscription=subscription,
        plan=plan,
        amount=amount,
        base_amount=base_amount,
        promotion=promotion,
        promotion_reason=(promotion.reason if promotion else ""),
        promotion_discount_amount=max(Decimal("0"), base_amount - amount),
        service_count=service_count,
        months=months,
        billing_cycle=billing_cycle,
        provider=provider,
        reference=f"SUB-{subscription.pk}-{uuid4().hex[:12].upper()}",
    )


@transaction.atomic
def mark_payment_paid(payment):
    # Re-read both rows under locks. Payment callbacks can arrive after a
    # founder has changed the subscription, so the object originally loaded
    # by the request may no longer represent the current entitlement state.
    payment = (
        SubscriptionPayment.objects.select_for_update()
        .select_related("subscription", "plan")
        .get(pk=payment.pk)
    )
    if payment.status == SubscriptionPayment.STATUS_PAID:
        return payment
    subscription = (
        BusinessSubscription.objects.select_for_update()
        .select_related("plan")
        .get(pk=payment.subscription_id)
    )
    now = timezone.now()
    payment.status = SubscriptionPayment.STATUS_PAID
    payment.paid_at = now
    payment.save(update_fields=["status", "paid_at"])

    # A stale payment request must not revoke a newer founder lifetime grant.
    # A payment created after that grant is still allowed to represent an
    # intentional, explicitly confirmed switch to another paid plan.
    if subscription.founder_lifetime and (
        subscription.founder_granted_at is None
        or payment.created_at <= subscription.founder_granted_at
    ):
        return payment

    subscription.plan = payment.plan
    subscription.status = BusinessSubscription.STATUS_ACTIVE
    subscription.founder_lifetime = False
    base = max([x for x in (subscription.paid_until, subscription.trial_ends_at, now) if x is not None])
    duration_days = 365 if payment.billing_cycle == SubscriptionPayment.CYCLE_YEARLY else 30 * payment.months
    subscription.paid_until = base + timezone.timedelta(days=duration_days)
    subscription.save()
    apply_subscription_entitlements(subscription)
    return payment
