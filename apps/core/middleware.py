from django.shortcuts import redirect
from django.urls import reverse

from .models import Business
from .context import set_current_business
from accounts.services import user_has_permission


class BusinessMiddleware:
    """Resolve a tenant from authenticated membership and session state."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Clear any previous request value before running membership queries.
        set_current_business(None)
        business = self._resolve_business(request)
        request.business = business
        set_current_business(business)
        try:
            return self.get_response(request)
        finally:
            set_current_business(None)

    @staticmethod
    def _resolve_business(request):
        if not getattr(request.user, "is_authenticated", False):
            return None

        from accounts.models import UserBusiness

        selected_id = request.session.get("active_business_id")
        if request.user.is_superuser:
            selected = Business.objects.filter(pk=selected_id).first() if selected_id else None
            business = selected or Business.objects.filter(slug="main").first() or Business.objects.order_by("id").first()
        else:
            memberships = UserBusiness.objects.filter(
                user=request.user, active=True, business__isnull=False
            ).select_related("business").order_by("business__name", "business_id")
            selected = memberships.filter(business_id=selected_id).first() if selected_id else None
            membership = selected or memberships.first()
            business = membership.business if membership else None
        if business:
            if selected_id != business.pk:
                request.session["active_business_id"] = business.pk
        else:
            if selected_id is not None:
                request.session.pop("active_business_id", None)
        return business


EXEMPT_PREFIXES = (
    "/accounts/login", "/accounts/logout", "/accounts/signup",
    "/business/settings", "/business/switch", "/admin", "/static",
)


class LoginRequiredMiddleware:
    """Requires login for every page except auth, admin, and static files."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(EXEMPT_PREFIXES):
            return redirect(f"{reverse('login')}?next={request.path}")
        if request.user.is_authenticated and not request.path.startswith(EXEMPT_PREFIXES):
            if not getattr(request, "business", None):
                from django.shortcuts import render
                return render(request, "accounts/no_business_access.html", status=403)
            module = _module_for_path(request.path)
            action = _action_for_request(request)
            if not user_has_permission(request.user, getattr(request, "business", None), module, action):
                from django.shortcuts import render
                return render(request, "403.html", status=403)
        return self.get_response(request)


MODULE_RULES = [
    ("/inventory", "inventory"),
    ("/procurement", "procurement"),
    ("/orders", "production"),
    ("/sales", "sales"),
    ("/expenses", "expenses"),
    ("/finance", "finance"),
    ("/reports", "reports"),
    ("/users", "users"),
    ("/business", "dashboard"),
]

def _module_for_path(path):
    for prefix, module in MODULE_RULES:
        if path == prefix or path.startswith(prefix + "/"):
            return module
    return "dashboard"

def _action_for_request(request):
    if request.method != "POST":
        path = request.path.rstrip("/")
        if any(token in path.split("/") for token in ("add", "edit", "delete", "approve", "reject", "complete", "receive", "dispense", "permissions")):
            return "edit"
        return "view"
    return "edit"
