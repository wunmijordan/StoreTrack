from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from core.models import Business


class CustomUserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required.")
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(username, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    # System roles are deliberately fixed identifiers. Their permissions are
    # stored/configurable in the Role tables; businesses may also create roles.
    ROLE_STOCK_KEEPER = "stock_keeper"
    ROLE_MANAGER = "manager"
    ROLE_ACCOUNTANT = "accountant"
    ROLE_MD_DIRECTOR = "md_director"
    ROLE_BUSINESS_ADMIN = "business_admin"
    ROLE_SUPERUSER = "superuser"
    SYSTEM_ROLE_DEFINITIONS = (
        (ROLE_STOCK_KEEPER, "Stock Keeper"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_ACCOUNTANT, "Accountant"),
        (ROLE_MD_DIRECTOR, "MD / Director"),
        (ROLE_BUSINESS_ADMIN, "Business Admin"),
        (ROLE_SUPERUSER, "Superuser"),
    )

    fullname = models.CharField(max_length=160)
    username = models.CharField(max_length=80, unique=True)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["fullname"]
    objects = CustomUserManager()

    class Meta:
        ordering = ["fullname", "username"]

    def __str__(self):
        return self.fullname or self.username

    def get_full_name(self):
        return self.fullname

    def get_short_name(self):
        return self.fullname.split()[0] if self.fullname else self.username


class Role(models.Model):
    """Business-scoped role definition.

    System roles are seeded from CustomUser.SYSTEM_ROLE_DEFINITIONS and cannot
    be deleted. Their permissions remain editable for each business. Custom
    roles are created by a superuser or Business Admin for that business.
    """
    key = models.SlugField(max_length=60)
    name = models.CharField(max_length=80)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="roles")
    is_system = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    visible_to_admin = models.BooleanField(
        default=True,
        help_text="Uncheck to keep this role visible only to the global superuser — for demo/review roles that aren't part of this business's normal operations. Business Admins won't see it in Roles & Access, can't open it directly, and can't assign it to a user.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["business", "key"], name="unique_role_key_per_business"),
            models.UniqueConstraint(fields=["business", "name"], name="unique_role_name_per_business"),
        ]

    def __str__(self):
        return self.name


class RoleModulePermission(models.Model):
    MODULE_CHOICES = [
        ("dashboard", "Dashboard"),
        ("inventory", "Inventory"),
        ("procurement", "Procurement"),
        ("production", "Production Orders"),
        ("sales", "Sales"),
        ("expenses", "Expenses"),
        ("finance", "Finance"),
        ("reports", "Reports"),
        ("users", "User Management"),
    ]
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="module_permissions")
    module = models.CharField(max_length=30, choices=MODULE_CHOICES)
    can_view = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)

    class Meta:
        ordering = ["module"]
        constraints = [
            models.UniqueConstraint(fields=["role", "module"], name="unique_role_module_permission"),
        ]


class UserBusiness(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="business_memberships")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="user_memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "business"], name="unique_user_business_membership"),
        ]

    def __str__(self):
        return f"{self.user} — {self.business} — {self.role}"


class UserModulePermission(models.Model):
    """Optional per-user override of role defaults."""
    membership = models.ForeignKey(UserBusiness, on_delete=models.CASCADE, related_name="module_permissions")
    module = models.CharField(max_length=30, choices=RoleModulePermission.MODULE_CHOICES)
    can_view = models.BooleanField(null=True, blank=True, default=None)
    can_edit = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["membership", "module"], name="unique_user_module_permission"),
        ]
        ordering = ["module"]

    def __str__(self):
        return f"{self.membership.user} — {self.get_module_display()}"