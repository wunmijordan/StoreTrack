from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from .forms import UserForm, PermissionMatrixForm, RoleForm, RolePermissionForm
from .models import CustomUser, Role, RoleModulePermission, UserBusiness
from .services import ensure_permissions, is_business_admin, seed_business_roles, user_has_permission


def can_manage(request):
    # User administration is deliberately reserved for the global superuser or
    # the Business Admin of the current business. A custom role with Users/Edit
    # cannot escalate itself into user administration.
    return request.user.is_superuser or is_business_admin(request.user, request.business)


def can_manage_roles(request):
    return request.user.is_superuser or is_business_admin(request.user, request.business)


@login_required
def users_list(request):
    if not can_manage(request):
        return render(request, "403.html", status=403)
    seed_business_roles(request.business)
    memberships = UserBusiness.objects.filter(business=request.business, active=True).select_related("user", "role").order_by("user__fullname")
    roles = Role.objects.filter(business=request.business, active=True).order_by("is_system", "name")
    return render(request, "accounts/users_list.html", {"memberships": memberships, "roles": roles, "can_manage_roles": can_manage_roles(request)})


@login_required
def user_form(request, pk=None):
    if not can_manage(request):
        return render(request, "403.html", status=403)
    obj = get_object_or_404(CustomUser, pk=pk) if pk else None
    membership = UserBusiness.objects.filter(user=obj, business=request.business).select_related("role").first() if obj else None
    if request.method == "POST":
        form = UserForm(request.POST, instance=obj, business=request.business, actor=request.user, membership=membership)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                role = form.cleaned_data["role"]
                membership, _ = UserBusiness.objects.get_or_create(user=user, business=request.business, defaults={"role": role, "active": user.is_active})
                membership.role = role
                membership.active = user.is_active
                membership.save(update_fields=["role", "active"])
                ensure_permissions(membership)
            messages.success(request, "User updated." if obj else "User created.")
            return redirect("users_list")
    else:
        form = UserForm(instance=obj, business=request.business, actor=request.user, membership=membership)
    return render(request, "accounts/user_form.html", {"form": form, "obj": obj})


@login_required
def user_permissions(request, pk):
    if not can_manage(request):
        return render(request, "403.html", status=403)
    membership = get_object_or_404(UserBusiness.objects.select_related("user", "role"), pk=pk, business=request.business)
    if request.method == "POST":
        form = PermissionMatrixForm(request.POST, membership=membership)
        if form.is_valid():
            form.save()
            messages.success(request, f"Permissions updated for {membership.user.fullname}.")
            return redirect("users_permissions", pk=membership.pk)
    else:
        form = PermissionMatrixForm(membership=membership)
    rows = [(m, label, form[f"{m}_view"], form[f"{m}_edit"]) for m, label in RoleModulePermission.MODULE_CHOICES]
    return render(request, "accounts/user_permissions.html", {"membership": membership, "form": form, "rows": rows})


@login_required
def roles_list(request):
    if not can_manage_roles(request):
        return render(request, "403.html", status=403)
    seed_business_roles(request.business)
    roles = Role.objects.filter(business=request.business)
    if not request.user.is_superuser:
        roles = roles.exclude(visible_to_admin=False)
    roles = roles.prefetch_related("module_permissions")
    return render(request, "accounts/roles_list.html", {"roles": roles})


@login_required
def role_form(request, pk=None):
    if not can_manage_roles(request):
        return render(request, "403.html", status=403)
    obj = get_object_or_404(Role, pk=pk, business=request.business) if pk else None
    if obj and obj.is_system and request.user.is_superuser is False and obj.key in (CustomUser.ROLE_BUSINESS_ADMIN, CustomUser.ROLE_SUPERUSER):
        return render(request, "403.html", status=403)
    # A role the superuser hid from admins (e.g. a demo/review role) is off
    # limits to anyone else, even by guessing its edit URL directly.
    if obj and not obj.visible_to_admin and not request.user.is_superuser:
        return render(request, "403.html", status=403)
    if request.method == "POST":
        form = RoleForm(request.POST, instance=obj, actor=request.user)
        if form.is_valid():
            role = form.save(commit=False)
            if not role.pk:
                base = slugify(role.name) or "custom-role"
                key = base
                n = 2
                while Role.objects.filter(business=request.business, key=key).exists():
                    key = f"{base}-{n}"; n += 1
                role.key = key
                role.business = request.business
                role.is_system = False
            role.save()
            for module, _ in RoleModulePermission.MODULE_CHOICES:
                RoleModulePermission.objects.get_or_create(role=role, module=module)
            messages.success(request, "Role created." if not obj else "Role updated.")
            return redirect("roles_list")
    else:
        form = RoleForm(instance=obj, actor=request.user)
    return render(request, "accounts/role_form.html", {"form": form, "obj": obj})


@login_required
def role_permissions(request, pk):
    if not can_manage_roles(request):
        return render(request, "403.html", status=403)
    role = get_object_or_404(Role, pk=pk, business=request.business)
    if not role.visible_to_admin and not request.user.is_superuser:
        return render(request, "403.html", status=403)
    if request.method == "POST":
        form = RolePermissionForm(request.POST, role=role)
        if form.is_valid():
            form.save()
            messages.success(request, f"Permissions updated for {role.name}.")
            return redirect("role_permissions", pk=role.pk)
    else:
        form = RolePermissionForm(role=role)
    rows = [(m, label, form[f"{m}_view"], form[f"{m}_edit"]) for m, label in RoleModulePermission.MODULE_CHOICES]
    return render(request, "accounts/role_permissions.html", {"role": role, "form": form, "rows": rows})