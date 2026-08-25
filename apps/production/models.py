from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class Order(BusinessOwnedModel):
    """A production order — either for a specific customer (made to order,
    delivered directly, never touches shelf stock) or a physical store
    restock (adds to shelf stock on completion, not tied to any customer).
    Approved and completed as a whole — all its line items together, not
    item-by-item. See docs/ARCHITECTURE.md for the full flow."""

    TYPE_CHOICES = [("distribution", "Distribution Order"), ("online", "Online Order"), ("physical_store", "Physical Store Order")]
    STATUS_CHOICES = [
        ("pending", "Pending"), ("approved", "Approved"),
        ("completed", "Completed"), ("rejected", "Rejected"),
    ]
    PAYMENT_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]

    date = models.DateField()
    order_type = models.CharField(max_length=15, choices=TYPE_CHOICES, default="physical_store")
    customer_name = models.CharField(max_length=120, blank=True,
        help_text="Required for distribution and online orders; leave blank for a physical store restock.")
    customer_region = models.CharField(max_length=100, blank=True,
        help_text="Optional reporting region/territory for distribution or online customer analytics.")
    customer_group = models.CharField(max_length=100, blank=True,
        help_text="Optional customer group/segment for distribution or online customer analytics.")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Cash",
        help_text="Relevant for distribution/online orders — recorded on the Sale created when this completes.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True)
    approved_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        who = self.customer_name if self.order_type in ("distribution", "online") else "Physical store"
        return f"Order #{self.id} — {who}"

    @property
    def total(self):
        return sum((i.line_total for i in self.items.all()), Decimal("0"))

    @property
    def total_units(self):
        return sum((i.total_units for i in self.items.all()), Decimal("0"))

    def material_requirements(self):
        """Raw material needed across every line item.

        Both recipe ingredients and per-production inputs (packaging, gas,
        production supplies) are included. Quantities are exact batch+piece
        requirements and are returned in each material's usage unit.
        """
        needed = {}
        for item in self.items.select_related("finished_good"):
            good = item.finished_good
            upb = good.units_per_batch or Decimal("1")
            per_piece_factor = item.piece_qty / upb

            links = list(good.recipe_items.select_related("raw_material"))
            links += list(good.production_materials.select_related("raw_material"))

            for link in links:
                qty = link.qty_per_batch * item.batch_qty
                qty += link.qty_per_batch * per_piece_factor
                mat = link.raw_material
                current = needed.get(mat.id)
                needed[mat.id] = (mat, (current[1] if current else Decimal("0")) + qty)
        return needed

    def shortages(self):
        result = []
        for mat, needed in self.material_requirements().values():
            if needed > mat.stock:
                result.append({
                    "name": mat.name,
                    "category": mat.get_category_display(),
                    "usage_unit": mat.usage_unit,
                    "needed": needed,
                    "have": mat.stock,
                    "short": needed - mat.stock,
                })
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