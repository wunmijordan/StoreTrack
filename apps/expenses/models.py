from decimal import Decimal

from django.conf import settings
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class Expense(BusinessOwnedModel):
    CATEGORY_CHOICES = [
        ("utilities", "Utilities"),
        ("rent", "Rent / Premises"),
        ("maintenance", "Maintenance / Repairs"),
        ("transport", "Transport / Delivery"),
        ("labour", "Labour / Wages"),
        ("marketing", "Marketing"),
        ("bank", "Bank / Payment Fees"),
        ("other", "Other"),
    ]

    date = models.DateField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")
    description = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    vendor = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses_created",
    )

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.description} — {self.amount}"
