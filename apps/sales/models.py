from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class Sale(BusinessOwnedModel):
    """Every row here represents a completed transaction — money already
    changed hands. Created two ways: directly via 'New Sale' (physical
    store stock, immediate), or automatically when a linked customer Order
    completes (see production.Order.complete). There's no pending state
    here — a customer order's pending/approved/completed lifecycle lives
    entirely on the Order; this only exists once that's already done."""

    PAYMENT_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]
    SOURCE_CHOICES = [("walkin", "Physical Store"), ("customer_order", "Customer Order")]

    date = models.DateField()
    customer = models.CharField(max_length=120, blank=True, default="Walk-in")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Cash")
    source = models.CharField(max_length=15, choices=SOURCE_CHOICES, default="walkin")
    linked_order = models.ForeignKey(
        "production.Order", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Set automatically if this sale was created from a completed customer order.",
    )

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Sale #{self.id} — {self.customer}"

    @property
    def total(self):
        return sum((i.line_total for i in self.items.all()), Decimal("0"))


class SaleItem(TimestampedModel):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    batch_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    piece_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0,
        help_text="Snapshot of the product's selling price at sale time — set automatically.")

    def __str__(self):
        return f"{self.sale.customer} — {self.finished_good.name} x{self.total_units}"

    @property
    def total_units(self):
        upb = self.finished_good.units_per_batch or Decimal("1")
        return self.batch_qty * upb + self.piece_qty

    @property
    def line_total(self):
        """Discount is applied PER UNIT, not once on the line total — e.g.
        50 units at 1500 with a 200 discount is (1500-200)*50 = 65,000,
        not 1500*50-200."""
        return self.total_units * ((self.price or Decimal("0")) - (self.discount or Decimal("0")))