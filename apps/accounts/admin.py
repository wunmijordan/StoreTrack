from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Role, RoleModulePermission, UserBusiness, UserModulePermission

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
