from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class PurchaseOrder(BusinessOwnedModel):
    STATUS_CHOICES = [("draft", "Draft"), ("ordered", "Ordered"), ("received", "Received")]
    PAYMENT_STATUS_CHOICES = [("paid", "Paid"), ("partial", "Partially Paid"), ("unpaid", "Unpaid")]
    PAYMENT_METHOD_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]

    date = models.DateField()
    supplier = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    received_date = models.DateField(null=True, blank=True)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default="paid")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default="Transfer")
    account = models.ForeignKey("core.CashAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_orders")

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


class SupplierPayment(BusinessOwnedModel):
    date = models.DateField()
    supplier = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=[("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")], default="Transfer")
    reference = models.CharField(max_length=80, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    account = models.ForeignKey("core.CashAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="supplier_payments")
    class Meta: ordering = ["-date", "-id"]
