from django.shortcuts import redirect
from django.urls import reverse

from .models import Business
from .context import set_current_business
from accounts.services import user_has_permission


class BusinessMiddleware:
    """Resolves the current business and attaches request.business.
    Single business today — this is the single place a real multi-location
    app would instead resolve tenancy from the host/path/session, the way
    ChurchForce's TenantMiddleware does."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        business = Business.default()
        request.business = business
        set_current_business(business)
        return self.get_response(request)


EXEMPT_PREFIXES = ("/accounts/login", "/accounts/logout", "/admin", "/static")


class LoginRequiredMiddleware:
    """Requires login for every page except auth, admin, and static files."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(EXEMPT_PREFIXES):
            return redirect(f"{reverse('login')}?next={request.path}")
        if request.user.is_authenticated and not request.path.startswith(EXEMPT_PREFIXES):
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
