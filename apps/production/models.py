from django.db import models
from core.models import BusinessOwnedModel


class ProductionRequest(BusinessOwnedModel):
    STATUS_CHOICES = [
        ("pending", "Pending"), ("in_production", "In production"),
        ("fulfilled", "Fulfilled"), ("cancelled", "Cancelled"),
    ]

    date = models.DateField()
    requested_by = models.CharField(max_length=120, help_text="e.g. Main Store")
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    needed_by = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.requested_by} wants {self.qty} x {self.finished_good}"


class ProductionOrder(BusinessOwnedModel):
    TYPE_CHOICES = [("internal", "Internal"), ("customer", "Customer")]
    STATUS_CHOICES = [("planned", "Planned"), ("completed", "Completed"), ("cancelled", "Cancelled")]

    date = models.DateField()
    order_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="internal")
    linked_request = models.ForeignKey(ProductionRequest, null=True, blank=True, on_delete=models.SET_NULL)
    customer_name = models.CharField(max_length=120, blank=True)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="planned")
    completed_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        who = self.customer_name if self.order_type == "customer" else "Internal"
        return f"Produce {self.qty} x {self.finished_good} ({who})"

    def shortages(self):
        result = []
        for ri in self.finished_good.recipe_items.select_related("raw_material"):
            needed = ri.qty_per_unit * self.qty
            have = ri.raw_material.stock
            if needed > have:
                result.append({"name": ri.raw_material.name, "needed": needed, "have": have, "short": needed - have})
        return result
