from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class Sale(BusinessOwnedModel):
    PAYMENT_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]

    date = models.DateField()
    customer = models.CharField(max_length=120, blank=True, default="Walk-in")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Cash")

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Sale #{self.id} — {self.customer}"

    @property
    def total(self):
        return sum((i.qty * i.price for i in self.items.all()), Decimal("0"))


class SaleItem(TimestampedModel):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def line_total(self):
        return self.qty * self.price
