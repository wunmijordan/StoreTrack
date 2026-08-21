from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class RawMaterial(BusinessOwnedModel):
    name = models.CharField(max_length=120)
    purchase_unit = models.CharField(max_length=20, default="", blank=True,
        help_text="What you buy — bag, carton, pack…")
    package_qty = models.DecimalField(max_digits=12, decimal_places=2, default=1,
        help_text="How much is inside ONE purchase unit. E.g. 1 bag = 50 → 50.")
    package_unit = models.CharField(max_length=20, default="", blank=True,
        help_text="The unit package_qty is measured in — kg, g, litre… (what's printed on the pack)")
    usage_unit = models.CharField(max_length=20, default="", blank=True,
        help_text="The fine unit recipes actually consume — kg, g, spoon, cap…")
    usage_conversion_factor = models.DecimalField(max_digits=12, decimal_places=2, default=1,
        help_text="How many usage units in ONE package_unit. Standard: kg→g is 1000, litre→ml is 1000, "
                   "same unit both ways is 1. Non-standard (spoon, cap…): count it yourself, e.g. "
                   "'my spoon holds 5g' → if package_unit is kg, that's 200 spoons per kg → 200.")
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_per_unit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["business", "name"], name="unique_raw_material_per_business")]

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.stock <= self.reorder_level

    @property
    def is_warning(self):
        """
        Triggers amber warning state if stock is above the reorder level,
        but less than or equal to 150% of the reorder level.
        """
        if self.is_low:
            return False
        return self.stock <= (self.reorder_level * Decimal("1.5"))

    @property
    def total_conversion_factor(self):
        """Usage units in ONE purchase unit — the number that actually
        matters for receiving stock and costing: package_qty (how much is
        in the pack) x usage_conversion_factor (how that content unit
        breaks down into the fine unit recipes use). E.g. flour: 50 (kg
        per bag) x 1 (kg->kg) = 50. Sugar: 50 (kg per bag) x 1000 (kg->g)
        = 50,000 (g per bag)."""
        return (self.package_qty or Decimal("1")) * (self.usage_conversion_factor or Decimal("1"))

    @property
    def has_unit_conversion(self):
        return bool(self.purchase_unit) and self.total_conversion_factor != 1

    @property
    def stock_breakdown(self):
        """Decomposes current stock (usage unit) into whole purchase units
        + remainder, e.g. 130kg at 50kg/bag -> (2, 30). Only meaningful when
        purchase and usage units actually differ."""
        factor = self.total_conversion_factor
        if factor <= 0:
            return None
        whole = int(self.stock // factor)
        remainder = self.stock - (whole * factor)
        return whole, remainder

    @property
    def cost_per_purchase_unit(self):
        """cost_per_unit is always stored per (fine) usage unit internally —
        what recipe costing and production deductions run on; this is just
        the purchase-unit-denominated view of the same number for display."""
        return self.cost_per_unit * self.total_conversion_factor


class FinishedGood(BusinessOwnedModel):
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=20, help_text="loaf, plate, box…")
    units_per_batch = models.DecimalField(max_digits=12, decimal_places=2, default=1,
        help_text="How many individual units one production batch makes, e.g. 41 loaves per batch. "
                   "Recipe quantities are per BATCH, not per unit. Leave at 1 if you don't produce in batches.")
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0,
        help_text="Physical store (shelf) stock — available to sell right now.")
    total_produced = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text="Cumulative all-time production (customer orders + physical store restocks). "
                   "Never decreases — a running total, not current stock.")
    total_delivered_to_customers = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text="Cumulative units delivered via completed customer orders. Only updates when an "
                   "order is completed — same timing as physical store stock, not when merely ordered.")
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0,
        help_text="In individual units, not batches.")
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["business", "name"], name="unique_finished_good_per_business")]

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.stock <= self.reorder_level

    @property
    def is_warning(self):
        """
        Triggers amber warning state if stock is above the reorder level,
        but less than or equal to 150% of the reorder level.
        """
        if self.is_low:
            return False
        return self.stock <= (self.reorder_level * Decimal("1.5"))

    @property
    def est_cost(self):
        """Estimated ingredient cost PER UNIT (matches selling_price being
        per unit) — recipe quantities are per batch, so this divides the
        batch cost back down by units_per_batch."""
        batch_cost = Decimal("0")
        for ri in self.recipe_items.select_related("raw_material"):
            batch_cost += ri.raw_material.cost_per_unit * ri.qty_per_batch
        upb = self.units_per_batch or Decimal("1")
        return batch_cost / upb


class RecipeItem(TimestampedModel):
    """Line item, not independently business-owned — scoped implicitly
    through finished_good. Quantities are PER BATCH of the finished good,
    not per individual unit — this matches how production actually happens
    (a whole batch of dough at once), not how it's shelved/sold."""
    finished_good = models.ForeignKey(FinishedGood, related_name="recipe_items", on_delete=models.CASCADE)
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE)
    qty_per_batch = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ("finished_good", "raw_material")

    def __str__(self):
        return f"{self.qty_per_batch} {self.raw_material.usage_unit} {self.raw_material.name} / batch of {self.finished_good.name}"