from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class PurchaseOrder(BusinessOwnedModel):
    STATUS_CHOICES = [("draft", "Draft"), ("ordered", "Ordered"), ("received", "Received")]

    date = models.DateField()
    supplier = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    received_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"PO #{self.id} — {self.supplier or 'Unnamed supplier'}"

    @property
    def total(self):
        return sum((i.qty * i.unit_cost for i in self.items.all()), Decimal("0"))


class PurchaseOrderItem(TimestampedModel):
    purchase_order = models.ForeignKey(PurchaseOrder, related_name="items", on_delete=models.CASCADE)
    raw_material = models.ForeignKey("inventory.RawMaterial", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def line_total(self):
        return self.qty * self.unit_cost
