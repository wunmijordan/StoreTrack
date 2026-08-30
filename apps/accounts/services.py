from django.db import transaction
from .models import CustomUser, Role, RoleModulePermission, UserBusiness, UserModulePermission

ROLE_DEFAULTS = {
    CustomUser.ROLE_STOCK_KEEPER: {
        "dashboard": (True, False), "inventory": (True, True), "procurement": (True, True),
        "production": (True, True), "sales": (True, False), "expenses": (False, False),
        "finance": (False, False), "reports": (True, False), "users": (False, False),
    },
    CustomUser.ROLE_MANAGER: {
        "dashboard": (True, False), "inventory": (True, True), "procurement": (True, True),
        "production": (True, True), "sales": (True, True), "expenses": (True, True),
        "finance": (True, True), "reports": (True, True), "users": (False, False),
    },
    CustomUser.ROLE_ACCOUNTANT: {
        "dashboard": (True, False), "inventory": (True, False), "procurement": (True, False),
        "production": (True, False), "sales": (True, False), "expenses": (True, True),
        "finance": (True, True), "reports": (True, True), "users": (False, False),
    },
    CustomUser.ROLE_MD_DIRECTOR: {
        "dashboard": (True, False), "inventory": (True, False), "procurement": (True, False),
        "production": (True, False), "sales": (True, False), "expenses": (True, False),
        "finance": (True, True), "reports": (True, True), "users": (True, False),
    },
    CustomUser.ROLE_BUSINESS_ADMIN: {m: (True, True) for m, _ in RoleModulePermission.MODULE_CHOICES},
    CustomUser.ROLE_SUPERUSER: {m: (True, True) for m, _ in RoleModulePermission.MODULE_CHOICES},
}


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


def user_has_permission(user, business, module, action="view"):
    if not getattr(user, "is_authenticated", False) or not business:
        return False
    if getattr(user, "is_superuser", False):
        return True
    membership = UserBusiness.objects.filter(user=user, business=business, active=True).select_related("role").first()
    if not membership:
        return False
    perm = membership.module_permissions.filter(module=module).first()
    if not perm:
        role_perm = membership.role.module_permissions.filter(module=module).first()
        if not role_perm:
            return False
        return role_perm.can_edit if action == "edit" else role_perm.can_view
    if action == "edit":
        return perm.can_edit if perm.can_edit is not None else membership.role.module_permissions.filter(module=module).values_list("can_edit", flat=True).first() is True
    return perm.can_view if perm.can_view is not None else membership.role.module_permissions.filter(module=module).values_list("can_view", flat=True).first() is True


def is_business_admin(user, business):
    if getattr(user, "is_superuser", False):
        return True
    membership = UserBusiness.objects.filter(user=user, business=business, active=True).select_related("role").first()
    return bool(membership and membership.role.key == CustomUser.ROLE_BUSINESS_ADMIN)