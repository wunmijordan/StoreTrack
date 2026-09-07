from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (BusinessFeatureAccess, BusinessModuleAccess, BusinessSubscription, CustomUser, Role, RoleModulePermission, SubscriptionPayment, SubscriptionPaymentSettings, SubscriptionPlan, SubscriptionPlanModule, SubscriptionService, UserBusiness, UserModulePermission)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    ordering = ("fullname",)
    list_display = ("fullname", "username", "email", "phone", "is_active", "is_superuser")
    fieldsets = ((None, {"fields": ("username", "password")}),
                 ("Personal", {"fields": ("fullname", "email", "phone")}),
                 ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
                 ("Dates", {"fields": ("last_login", "date_joined")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("fullname", "username", "email", "phone", "password1", "password2", "is_active", "is_staff", "is_superuser")}),)
    search_fields = ("fullname", "username", "email", "phone")

admin.site.register(Role)
admin.site.register(RoleModulePermission)
admin.site.register(UserBusiness)
admin.site.register(UserModulePermission)
admin.site.register(BusinessModuleAccess)

admin.site.register(SubscriptionPlan)
admin.site.register(SubscriptionPlanModule)
admin.site.register(BusinessSubscription)
admin.site.register(SubscriptionService)
admin.site.register(BusinessFeatureAccess)
admin.site.register(SubscriptionPayment)
admin.site.register(SubscriptionPaymentSettings)
