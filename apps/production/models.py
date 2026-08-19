from decimal import Decimal, ROUND_CEILING
from django.db import models
from core.models import BusinessOwnedModel


class ProductionRequest(BusinessOwnedModel):
    STATUS_CHOICES = [
        ("pending", "Pending"), ("in_production", "In production"),
        ("fulfilled", "Fulfilled"), ("cancelled", "Cancelled"),
    ]

    date = models.DateField()
    requested_by = models.CharField(max_length=120, help_text="e.g. Main Store", blank=True)
    linked_sale_item = models.ForeignKey(
        "sales.SaleItem", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="production_requests",
        help_text="If this request exists to fulfil a customer order, which order line it's for. "
                   "Product and quantity are then taken from that order, not entered here.",
    )
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    needed_by = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        who = self.linked_sale_item.sale.customer if self.linked_sale_item else self.requested_by
        return f"{who} wants {self.qty} x {self.finished_good}"


class ProductionOrder(BusinessOwnedModel):
    TYPE_CHOICES = [("internal", "Internal"), ("customer", "Customer")]
    STATUS_CHOICES = [("planned", "Planned"), ("completed", "Completed"), ("cancelled", "Cancelled")]

    date = models.DateField()
    order_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="internal")
    linked_request = models.ForeignKey(ProductionRequest, null=True, blank=True, on_delete=models.SET_NULL)
    customer_name = models.CharField(max_length=120, blank=True)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2,
        help_text="In individual units — production is automatically rounded up to whole batches.")
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="planned")
    completed_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        who = self.customer_name if self.order_type == "customer" else "Internal"
        return f"Produce {self.qty} x {self.finished_good} ({who})"

    @property
    def batches_needed(self):
        """Whole batches required to cover qty units, rounded UP — you
        can't make a fractional batch, so any surplus beyond qty becomes
        shelf stock."""
        upb = self.finished_good.units_per_batch or Decimal("1")
        if upb <= 0:
            upb = Decimal("1")
        return (self.qty / upb).to_integral_value(rounding=ROUND_CEILING)

    @property
    def units_to_produce(self):
        """Actual units added to stock on completion — batches_needed x
        units_per_batch, which may exceed qty when it doesn't divide evenly."""
        upb = self.finished_good.units_per_batch or Decimal("1")
        return self.batches_needed * upb

    def shortages(self):
        """Raw material shortfall to cover batches_needed — recipe
        quantities are per batch, not per unit."""
        batches = self.batches_needed
        result = []
        for ri in self.finished_good.recipe_items.select_related("raw_material"):
            needed = ri.qty_per_batch * batches
            have = ri.raw_material.stock
            if needed > have:
                result.append({"name": ri.raw_material.name, "needed": needed, "have": have, "short": needed - have})
        return result
