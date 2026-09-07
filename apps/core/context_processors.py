from accounts.models import RoleModulePermission, UserBusiness
from accounts.services import is_business_admin, user_has_permission
from accounts.subscription_services import business_has_feature
from .models import Business
from .verticals import vertical_config

def business(request):
    biz = getattr(request, "business", None)
    permissions = {}
    if getattr(request.user, "is_authenticated", False) and biz:
        for module, _ in RoleModulePermission.MODULE_CHOICES:
            permissions[module] = {
                "view": user_has_permission(request.user, biz, module, "view"),
                "edit": user_has_permission(request.user, biz, module, "edit"),
            }
    available_businesses = []
    can_manage_business = False
    if getattr(request.user, "is_authenticated", False):
        if request.user.is_superuser:
            available_businesses = Business.objects.order_by("name", "id")
        else:
            available_businesses = Business.objects.filter(
                user_memberships__user=request.user,
                user_memberships__active=True,
            ).distinct().order_by("name", "id")
        can_manage_business = bool(biz and is_business_admin(request.user, biz))
    subscription = None
    if biz and getattr(request.user, "is_authenticated", False):
        try:
            from accounts.models import BusinessSubscription
            service = getattr(biz, "subscription_service", None)
            subscription = service.subscription if service else BusinessSubscription.objects.filter(primary_business=biz).select_related("plan").first()
        except Exception:
            subscription = None
    return {
        "biz": biz,
        "module_permissions": permissions,
        "available_businesses": available_businesses,
        "can_manage_business": can_manage_business,
        "vertical_ui": vertical_config(biz),
        "subscription": subscription,
        "reports_full": business_has_feature(biz, "reports_full") if biz else False,
    }
