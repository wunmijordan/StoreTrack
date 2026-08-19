from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class Sale(BusinessOwnedModel):
    PAYMENT_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]
    ORDER_TYPE_CHOICES = [
        ("walkin", "Walk-in (from stock)"),
        ("customer_order", "Customer order (needs production)"),
    ]
    STATUS_CHOICES = [("pending", "Pending"), ("fulfilled", "Fulfilled")]

    date = models.DateField()
    customer = models.CharField(max_length=120, blank=True, default="Walk-in")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Cash")
    order_type = models.CharField(max_length=15, choices=ORDER_TYPE_CHOICES, default="walkin")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="fulfilled",
        help_text="Walk-in sales are fulfilled immediately. Customer orders start pending and "
                   "flip to fulfilled automatically when their linked production completes.")

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Sale #{self.id} — {self.customer}"

    @property
    def total(self):
        return sum((i.qty * i.price for i in self.items.all()), Decimal("0"))

    @property
    def is_fully_linked_to_production(self):
        """True if every line item has a linked (non-cancelled) production
        request — used to sanity-check before flipping status."""
        return all(
            item.production_requests.exclude(status="cancelled").exists()
            for item in self.items.all()
        )

    def refresh_fulfillment_status(self):
        """Call after a linked production request's order completes. Flips
        this sale to fulfilled once every line item's linked production
        request is fulfilled — not before, so a multi-product order only
        clears once the whole thing is actually ready."""
        if self.order_type != "customer_order" or self.status == "fulfilled":
            return
        items = list(self.items.all())
        if not items:
            return
        for item in items:
            req = item.production_requests.exclude(status="cancelled").first()
            if not req or req.status != "fulfilled":
                return
        self.status = "fulfilled"
        self.save(update_fields=["status"])


class SaleItem(TimestampedModel):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.sale.customer} — {self.finished_good.name} x{self.qty} ({self.sale.date})"

    @property
    def line_total(self):
        return self.qty * self.price
