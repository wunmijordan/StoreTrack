from django.shortcuts import redirect
from django.urls import reverse

from .models import Business
from .context import set_current_business


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
        return self.get_response(request)
