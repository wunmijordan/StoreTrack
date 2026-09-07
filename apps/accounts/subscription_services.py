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
    SubscriptionService,
    UserBusiness,
)
from .services import ensure_permissions, seed_business_roles


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


@transaction.atomic
def ensure_default_plans():
    names = {
        SubscriptionPlan.CODE_STARTER: "STARTER",
        SubscriptionPlan.CODE_PRODUCTION: "PRODUCTION",
        SubscriptionPlan.CODE_BUSINESS_PRO: "BUSINESS PRO",
    }
    plans = {}
    for code, name in names.items():
        plan, _ = SubscriptionPlan.objects.get_or_create(
            code=code,
            defaults={"name": name, "trial_days": 30, "monthly_price": Decimal("0.00")},
        )
        if plan.trial_days != 30:
            plan.trial_days = 30
            plan.save(update_fields=["trial_days"])
        for module, _label in RoleModulePermission.MODULE_CHOICES:
            level = PLAN_MATRIX[code].get(module, "none")
            SubscriptionPlanModule.objects.update_or_create(
                plan=plan,
                module=module,
                defaults={"enabled": level != "none", "level": level},
            )
        plans[code] = plan
    return plans


def business_has_feature(business, feature):
    if not business:
        return False
    row = BusinessFeatureAccess.objects.filter(business=business, feature=feature).values_list("enabled", flat=True).first()
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


def payment_amount(plan, service_count, months=1, billing_cycle="monthly"):
    service_count = max(1, int(service_count or 1))
    monthly_total = plan.monthly_price + Decimal(service_count - 1) * plan.additional_service_monthly_price
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
    amount = payment_amount(plan, subscription.services.count(), months, billing_cycle=billing_cycle)
    if amount <= 0:
        raise ValidationError("This plan does not yet have a payable price configured. Contact the StoreTrack founder/superuser.")
    return SubscriptionPayment.objects.create(
        subscription=subscription,
        plan=plan,
        amount=amount,
        service_count=max(1, subscription.services.count()),
        months=months,
        billing_cycle=billing_cycle,
        provider=provider,
        reference=f"SUB-{subscription.pk}-{uuid4().hex[:12].upper()}",
    )


@transaction.atomic
def mark_payment_paid(payment):
    if payment.status == SubscriptionPayment.STATUS_PAID:
        return payment
    now = timezone.now()
    payment.status = SubscriptionPayment.STATUS_PAID
    payment.paid_at = now
    payment.save(update_fields=["status", "paid_at"])
    subscription = payment.subscription
    subscription.plan = payment.plan
    subscription.status = BusinessSubscription.STATUS_ACTIVE
    subscription.founder_lifetime = False
    base = max([x for x in (subscription.paid_until, subscription.trial_ends_at, now) if x is not None])
    duration_days = 365 if payment.billing_cycle == SubscriptionPayment.CYCLE_YEARLY else 30 * payment.months
    subscription.paid_until = base + timezone.timedelta(days=duration_days)
    subscription.save()
    apply_subscription_entitlements(subscription)
    return payment
