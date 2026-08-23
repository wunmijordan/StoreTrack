from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class Order(BusinessOwnedModel):
    """A production order — either for a specific customer (made to order,
    delivered directly, never touches shelf stock) or a physical store
    restock (adds to shelf stock on completion, not tied to any customer).
    Approved and completed as a whole — all its line items together, not
    item-by-item. See docs/ARCHITECTURE.md for the full flow."""

    TYPE_CHOICES = [("customer", "Customer Order"), ("physical_store", "Physical Store Order")]
    STATUS_CHOICES = [
        ("pending", "Pending"), ("approved", "Approved"),
        ("completed", "Completed"), ("rejected", "Rejected"),
    ]
    PAYMENT_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]

    date = models.DateField()
    order_type = models.CharField(max_length=15, choices=TYPE_CHOICES, default="physical_store")
    customer_name = models.CharField(max_length=120, blank=True,
        help_text="Required for a customer order; leave blank for a physical store restock.")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Cash",
        help_text="Only relevant for customer orders — recorded on the Sale created when this completes.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True)
    approved_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        who = self.customer_name if self.order_type == "customer" else "Physical store"
        return f"Order #{self.id} — {who}"

    @property
    def total(self):
        return sum((i.line_total for i in self.items.all()), Decimal("0"))

    @property
    def total_units(self):
        return sum((i.total_units for i in self.items.all()), Decimal("0"))

    def material_requirements(self):
        """Raw material needed across every line item, using the exact
        batch+piece formula — no batch rounding, so no surplus production.
        Returns {raw_material: needed_qty}."""
        needed = {}
        for item in self.items.select_related("finished_good"):
            upb = item.finished_good.units_per_batch or Decimal("1")
            for ri in item.finished_good.recipe_items.select_related("raw_material"):
                per_piece = ri.qty_per_batch / upb
                qty = ri.qty_per_batch * item.batch_qty + per_piece * item.piece_qty
                mat = ri.raw_material
                needed[mat.id] = needed.get(mat.id, (mat, Decimal("0")))
                needed[mat.id] = (mat, needed[mat.id][1] + qty)
        return needed

    def shortages(self):
        result = []
        for mat, needed in self.material_requirements().values():
            if needed > mat.stock:
                result.append({"name": mat.name, "usage_unit": mat.usage_unit, "needed": needed, "have": mat.stock, "short": needed - mat.stock})
        return result


class OrderItem(TimestampedModel):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    batch_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    piece_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0,
        help_text="Snapshot of the product's selling price at order time — set automatically.")

    def __str__(self):
        return f"{self.finished_good.name} — {self.total_units} units"

    @property
    def total_units(self):
        upb = self.finished_good.units_per_batch or Decimal("1")
        return self.batch_qty * upb + self.piece_qty

    @property
    def line_total(self):
        """Discount is applied PER UNIT, not once on the line total — e.g.
        50 units at 1500 with a 200 discount is (1500-200)*50 = 65,000,
        not 1500*50-200. Matches how a per-item price cut actually works."""
        return self.total_units * ((self.price or Decimal("0")) - (self.discount or Decimal("0")))