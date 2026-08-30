from django.conf import settings
from django.db import models
from decimal import Decimal
from .context import get_current_business_id


class Business(models.Model):
    """The tenant root. One row today (single business); the structure is
    ready for multiple locations/franchises later without a model rewrite —
    see docs/ARCHITECTURE.md."""
    name = models.CharField(max_length=120, default="My Business")
    currency_symbol = models.CharField(max_length=5, default="₦")
    slug = models.SlugField(max_length=60, unique=True, default="main")

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self):
        return self.name

    @classmethod
    def default(cls):
        """Returns the single business row, creating it on first run.
        This is the one place a real multi-business setup would instead
        resolve 'which business' from the request (subdomain, path, session —
        see ChurchForce's TenantMiddleware for the fuller pattern)."""
        obj, _ = cls.objects.get_or_create(slug="main", defaults={"name": "My Business"})
        try:
            from accounts.services import seed_business_roles
            seed_business_roles(obj)
        except Exception:
            # Keep model import/bootstrap safe before migrations are complete.
            pass
        return obj


class BaseModel(models.Model):
    class Meta:
        abstract = True


class TimestampedModel(BaseModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BusinessManager(models.Manager):
    """Scoped manager: filters to the business resolved by BusinessMiddleware
    for the current request. With one business today this filter is a no-op
    in practice, but every model using this manager is already structured
    for multi-location — the filtering becomes real the day Business stops
    being a single row."""

    def get_queryset(self):
        qs = super().get_queryset()
        business_id = get_current_business_id()
        if business_id is not None:
            qs = qs.filter(business_id=business_id)
        return qs


class BusinessOwnedModel(TimestampedModel):
    """Base for any model that belongs to a business. Mirrors ChurchOwnedModel:
    a scoped default manager plus an explicit unscoped manager for admin,
    management commands, and provisioning — see rule in CLAUDE.md."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_set")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(app_label)s_%(class)s_created",
        help_text="Who made this entry. Null for records created before this field existed.",
    )

    objects = BusinessManager()
    raw_objects = models.Manager()

    class Meta:
        abstract = True

class CashAccount(BusinessOwnedModel):
    """A cash/bank/card ledger account used for actual money movement."""
    ACCOUNT_CHOICES = [("cash", "Cash"), ("bank", "Bank / Transfer"), ("card", "Card / POS"), ("other", "Other")]
    name = models.CharField(max_length=80)
    account_type = models.CharField(max_length=10, choices=ACCOUNT_CHOICES, default="cash")
    opening_balance = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["business", "name"], name="unique_cash_account_per_business")]
        ordering = ["name"]
    def __str__(self): return self.name
    @property
    def balance(self):
        return self.opening_balance + sum((t.signed_amount for t in self.transactions.all()), Decimal("0"))


class FinancialTransaction(BusinessOwnedModel):
    """Immutable-style cash ledger entry. Positive income, negative outflow."""
    INCOME = "income"
    OUTFLOW = "outflow"
    TYPE_CHOICES = [(INCOME, "Money In"), (OUTFLOW, "Money Out")]
    date = models.DateField()
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=255)
    payment_method = models.CharField(max_length=20, blank=True, default="")
    reference = models.CharField(max_length=80, blank=True, default="")
    account = models.ForeignKey(CashAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="transactions")
    reversed = models.BooleanField(default=False)
    reversal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal_entries")
    class Meta:
        ordering = ["-date", "-id"]
    @property
    def signed_amount(self): return self.amount if self.transaction_type == self.INCOME else -self.amount


class AuditLog(BusinessOwnedModel):
    """Human-readable audit trail for important business mutations."""
    action = models.CharField(max_length=30)
    model_name = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80, blank=True, default="")
    description = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    class Meta:
        ordering = ["-created_at", "-id"]
