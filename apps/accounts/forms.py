from django import forms
from django.contrib.auth import password_validation
from django.utils.text import slugify
from .models import CustomUser, Role, RoleModulePermission, UserBusiness, UserModulePermission
from .services import ensure_permissions, is_business_admin, seed_business_roles

CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text="Required for a new user; leave blank when editing to keep the current password.")
    role = forms.ModelChoiceField(queryset=Role.objects.none(), empty_label=None)

    class Meta:
        model = CustomUser
        fields = ["fullname", "username", "email", "phone", "role", "password", "is_active"]

    def __init__(self, *args, business, actor, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business
        self.actor = actor
        self.membership = membership
        seed_business_roles(business)
        qs = Role.objects.filter(business=business, active=True).order_by("is_system", "name")
        if not actor.is_superuser:
            qs = qs.exclude(key=CustomUser.ROLE_SUPERUSER)
            # A Business Admin is delegated authority for ordinary business users,
            # but only the global superuser may appoint another Business Admin.
            if is_business_admin(actor, business):
                qs = qs.exclude(key=CustomUser.ROLE_BUSINESS_ADMIN)
            # Roles the superuser marked hidden (e.g. a demo/review role) are
            # never assignable by a Business Admin, even by URL/ID guessing.
            qs = qs.exclude(visible_to_admin=False)
        self.fields["role"].queryset = qs
        for f in self.fields.values():
            f.widget.attrs["class"] = CLS
        if membership:
            self.fields["role"].initial = membership.role_id

    def clean_password(self):
        value = self.cleaned_data.get("password")
        if value and self.instance.pk:
            password_validation.validate_password(value, self.instance)
        return value

    def clean(self):
        c = super().clean()
        if not c.get("email") and not c.get("phone"):
            raise forms.ValidationError("Provide at least an email address or phone number.")
        if not self.instance.pk and not c.get("password"):
            self.add_error("password", "A password is required for a new user.")
        role = c.get("role")
        if role and role.key == CustomUser.ROLE_SUPERUSER and not self.actor.is_superuser:
            self.add_error("role", "Only the global superuser can create or assign a Superuser role.")
        if role and role.key == CustomUser.ROLE_BUSINESS_ADMIN and not self.actor.is_superuser:
            self.add_error("role", "Only the global superuser can appoint a Business Admin.")
        return c

    def save(self, commit=True):
        obj = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            obj.set_password(password)
        if commit:
            obj.save()
        return obj


class PermissionMatrixForm(forms.Form):
    def __init__(self, *args, membership, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership
        ensure_permissions(membership)
        for module, label in RoleModulePermission.MODULE_CHOICES:
            p = membership.module_permissions.get(module=module)
            role_p = membership.role.module_permissions.filter(module=module).first()
            self.fields[f"{module}_view"] = forms.BooleanField(required=False, label=f"{label}: View", initial=p.can_view if p.can_view is not None else (role_p.can_view if role_p else False))
            self.fields[f"{module}_edit"] = forms.BooleanField(required=False, label=f"{label}: Edit", initial=p.can_edit if p.can_edit is not None else (role_p.can_edit if role_p else False))
            self.fields[f"{module}_view"].widget.attrs["class"] = "h-4 w-4 accent-[#8f172d]"
            self.fields[f"{module}_edit"].widget.attrs["class"] = "h-4 w-4 accent-[#8f172d]"

    def save(self):
        for module, _ in RoleModulePermission.MODULE_CHOICES:
            UserModulePermission.objects.update_or_create(
                membership=self.membership, module=module,
                defaults={"can_view": self.cleaned_data.get(f"{module}_view", False),
                          "can_edit": self.cleaned_data.get(f"{module}_edit", False)}
            )


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name", "active", "visible_to_admin"]
        widgets = {
            "name": forms.TextInput(attrs={"class": CLS}),
            "active": forms.CheckboxInput(attrs={"class": "h-4 w-4 accent-[#8f172d]"}),
            "visible_to_admin": forms.CheckboxInput(attrs={"class": "h-4 w-4 accent-[#8f172d]"}),
        }

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the global superuser may create/keep a role hidden from the
        # Business Admin. Anyone else never even sees the field, so a role
        # they create or edit always stays at the model default (visible).
        if not (actor and actor.is_superuser):
            del self.fields["visible_to_admin"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Role name is required.")
        return name


class RolePermissionForm(forms.Form):
    def __init__(self, *args, role, **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role
        for module, label in RoleModulePermission.MODULE_CHOICES:
            p = role.module_permissions.filter(module=module).first()
            self.fields[f"{module}_view"] = forms.BooleanField(required=False, label=f"{label}: View", initial=p.can_view if p else False)
            self.fields[f"{module}_edit"] = forms.BooleanField(required=False, label=f"{label}: Edit", initial=p.can_edit if p else False)
            self.fields[f"{module}_view"].widget.attrs["class"] = "h-4 w-4 accent-[#8f172d]"
            self.fields[f"{module}_edit"].widget.attrs["class"] = "h-4 w-4 accent-[#8f172d]"

    def save(self):
        for module, _ in RoleModulePermission.MODULE_CHOICES:
            RoleModulePermission.objects.update_or_create(
                role=self.role, module=module,
                defaults={"can_view": self.cleaned_data.get(f"{module}_view", False),
                          "can_edit": self.cleaned_data.get(f"{module}_edit", False)}
            )