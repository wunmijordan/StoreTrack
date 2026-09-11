from django.db import transaction
from .models import (
    BusinessModuleAccess,
    BusinessSubscription,
    CustomUser,
    Role,
    RoleModulePermission,
    SubscriptionService,
    UserBusiness,
    UserModulePermission,
)

ROLE_DEFAULTS = {
    CustomUser.ROLE_STOCK_KEEPER: {
        "dashboard": (True, False), "inventory": (True, True), "procurement": (True, True),
        "production": (True, True), "sales": (True, False), "expenses": (False, False),
        "finance": (False, False), "reports": (True, False), "users": (False, False), "commerce": (False, False),
    },
    CustomUser.ROLE_MANAGER: {
        "dashboard": (True, False), "inventory": (True, True), "procurement": (True, True),
        "production": (True, True), "sales": (True, True), "expenses": (True, True),
        "finance": (True, True), "reports": (True, True), "users": (False, False), "commerce": (False, False),
    },
    CustomUser.ROLE_ACCOUNTANT: {
        "dashboard": (True, False), "inventory": (True, False), "procurement": (True, False),
        "production": (True, False), "sales": (True, False), "expenses": (True, True),
        "finance": (True, True), "reports": (True, True), "users": (False, False), "commerce": (False, False),
    },
    CustomUser.ROLE_MD_DIRECTOR: {
        "dashboard": (True, False), "inventory": (True, False), "procurement": (True, False),
        "production": (True, False), "sales": (True, False), "expenses": (True, False),
        "finance": (True, True), "reports": (True, True), "users": (True, False), "commerce": (False, False),
    },
    CustomUser.ROLE_BUSINESS_ADMIN: {m: (True, True) for m, _ in RoleModulePermission.MODULE_CHOICES},
    CustomUser.ROLE_SUPERUSER: {m: (True, True) for m, _ in RoleModulePermission.MODULE_CHOICES},
}


def _request_cache():
    """Return this request's cache, or None outside request handling."""
    from core.context import get_request_cache

    return get_request_cache()


def invalidate_business_access_cache(business):
    """Discard request-local entitlement data after an in-request mutation."""
    cache = _request_cache()
    if cache is None or not business:
        return
    for namespace in (
        "business_subscription",
        "business_module_access",
        "business_feature_access",
    ):
        cache.pop((namespace, business.pk), None)


def business_subscription_for(business):
    """Resolve a primary or additional service's subscription once per request."""
    if not business:
        return None
    cache = _request_cache()
    key = ("business_subscription", business.pk)
    if cache is not None and key in cache:
        return cache[key]

    service = (
        SubscriptionService.objects.filter(business=business)
        .select_related("subscription__plan")
        .first()
    )
    subscription = service.subscription if service else (
        BusinessSubscription.objects.filter(primary_business=business)
        .select_related("plan")
        .first()
    )
    if cache is not None:
        cache[key] = subscription
    return subscription


def _permission_snapshot(user, business):
    """Load one membership and both permission layers in three bounded queries."""
    cache = _request_cache()
    key = ("permission_snapshot", user.pk, business.pk)
    if cache is not None and key in cache:
        return cache[key]

    membership = (
        UserBusiness.objects.filter(user=user, business=business, active=True)
        .select_related("role")
        .prefetch_related("module_permissions", "role__module_permissions")
        .first()
    )
    if membership:
        user_permissions = {permission.module: permission for permission in membership.module_permissions.all()}
        role_permissions = {permission.module: permission for permission in membership.role.module_permissions.all()}
    else:
        user_permissions = {}
        role_permissions = {}
    snapshot = membership, user_permissions, role_permissions
    if cache is not None:
        cache[key] = snapshot
    return snapshot


def role_key(role):
    return role.key if role else CustomUser.ROLE_STOCK_KEEPER


@transaction.atomic
def seed_business_roles(business):
    roles = {}
    for key, name in CustomUser.SYSTEM_ROLE_DEFINITIONS:
        role, _ = Role.objects.get_or_create(
            business=business, key=key,
            defaults={"name": name, "is_system": True, "visible_to_admin": key != CustomUser.ROLE_SUPERUSER},
        )
        if not role.is_system:
            role.is_system = True
            role.save(update_fields=["is_system"])
        # The Superuser role is reserved for the global superuser. Force it
        # hidden even if it was seeded before this restriction existed, or if
        # someone flips it back on directly in the DB.
        if key == CustomUser.ROLE_SUPERUSER and role.visible_to_admin:
            role.visible_to_admin = False
            role.save(update_fields=["visible_to_admin"])
        # Keep system role labels aligned only on first creation; businesses may
        # rename labels later without losing their fixed system key.
        defaults = ROLE_DEFAULTS.get(key, {})
        for module, _label in RoleModulePermission.MODULE_CHOICES:
            view, edit = defaults.get(module, (False, False))
            RoleModulePermission.objects.get_or_create(
                role=role, module=module,
                defaults={"can_view": view, "can_edit": edit},
            )
        roles[key] = role
    return roles


def ensure_permissions(membership):
    """Create user overrides only when they don't exist; role defaults remain authoritative otherwise."""
    seed_business_roles(membership.business)
    for module, _ in RoleModulePermission.MODULE_CHOICES:
        UserModulePermission.objects.get_or_create(membership=membership, module=module)


def seed_business_modules(business, source=BusinessModuleAccess.SOURCE_DEFAULT):
    """Provision today's full module set behind the future plan boundary."""
    for module, _label in RoleModulePermission.MODULE_CHOICES:
        BusinessModuleAccess.objects.get_or_create(
            business=business,
            module=module,
            defaults={"enabled": module != "commerce", "source": source},
        )
    invalidate_business_access_cache(business)


def business_has_module(business, module):
    """Return the business entitlement. Explicit disabled rows are a hard ceiling.

    Legacy businesses with no subscription keep the historical missing-row=enabled
    rule. Once a subscription exists, expiry is enforced dynamically even before
    a scheduled entitlement refresh runs. Dashboard remains available; the
    dedicated Plans/Billing URLs are separately whitelisted as the recovery surface.
    """
    if not business:
        return False
    subscription = business_subscription_for(business)
    if subscription and not subscription.is_effectively_active and module != "dashboard":
        return False
    # Production is a vertical capability as well as a plan entitlement.
    # Wholesale and retail keep any historical production data intact, but do
    # not expose or authorize the production workflow while using a stock-first
    # vertical.
    if module == "production" and not business.uses_production:
        return False
    cache = _request_cache()
    access_key = ("business_module_access", business.pk)
    if cache is not None and access_key in cache:
        module_access = cache[access_key]
    else:
        module_access = dict(
            BusinessModuleAccess.objects.filter(business=business).values_list("module", "enabled")
        )
        if cache is not None:
            cache[access_key] = module_access
    enabled = module_access.get(module)
    return enabled is not False


def user_has_permission(user, business, module, action="view"):
    if not getattr(user, "is_authenticated", False) or not business:
        return False
    if not business_has_module(business, module):
        return False
    if getattr(user, "is_superuser", False):
        return True
    membership, user_permissions, role_permissions = _permission_snapshot(user, business)
    if not membership:
        return False
    perm = user_permissions.get(module)
    if not perm:
        role_perm = role_permissions.get(module)
        if not role_perm:
            return False
        return role_perm.can_edit if action == "edit" else role_perm.can_view
    if action == "edit":
        role_perm = role_permissions.get(module)
        return perm.can_edit if perm.can_edit is not None else bool(role_perm and role_perm.can_edit)
    role_perm = role_permissions.get(module)
    return perm.can_view if perm.can_view is not None else bool(role_perm and role_perm.can_view)


def is_business_admin(user, business):
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_authenticated", False) or not business:
        return False
    membership, _user_permissions, _role_permissions = _permission_snapshot(user, business)
    return bool(membership and membership.role.key == CustomUser.ROLE_BUSINESS_ADMIN)
