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


class RawMaterialCostSnapshot(BusinessOwnedModel):
    """Historical procurement price that becomes available when a purchase is received.

    Production costing uses the latest received snapshot at the production date;
    it never averages older procurement prices into the production cost.
    """
    raw_material = models.ForeignKey("inventory.RawMaterial", related_name="cost_snapshots", on_delete=models.PROTECT)
    purchase_order_item = models.ForeignKey(PurchaseOrderItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_snapshots")
    effective_date = models.DateField()
    purchase_unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    usage_unit_cost = models.DecimalField(max_digits=16, decimal_places=6)
    supplier = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-effective_date", "-id"]

    def __str__(self):
        return f"{self.raw_material.name} — {self.purchase_unit_cost} / {self.raw_material.purchase_unit} — {self.effective_date}"
