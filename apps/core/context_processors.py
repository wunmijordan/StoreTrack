from accounts.models import RoleModulePermission, UserBusiness
from accounts.services import user_has_permission

def business(request):
    biz = getattr(request, "business", None)
    permissions = {}
    if getattr(request.user, "is_authenticated", False) and biz:
        for module, _ in RoleModulePermission.MODULE_CHOICES:
            permissions[module] = {
                "view": user_has_permission(request.user, biz, module, "view"),
                "edit": user_has_permission(request.user, biz, module, "edit"),
            }
    return {"biz": biz, "module_permissions": permissions}