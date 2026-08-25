from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("", include("core.urls")),
    path("inventory/", include("inventory.urls")),
    path("procurement/", include("procurement.urls")),
    path("", include("production.urls")),
    path("sales/", include("sales.urls")),
    path("expenses/", include("expenses.urls")),
]
