from django.db import models
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

    objects = BusinessManager()
    raw_objects = models.Manager()

    class Meta:
        abstract = True
