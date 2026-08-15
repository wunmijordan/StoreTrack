from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class RawMaterial(BusinessOwnedModel):
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=20, help_text="kg, litre, pack…")
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


class FinishedGood(BusinessOwnedModel):
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=20, help_text="loaf, plate, box…")
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
    def est_cost(self):
        total = Decimal("0")
        for ri in self.recipe_items.select_related("raw_material"):
            total += ri.raw_material.cost_per_unit * ri.qty_per_unit
        return total


class RecipeItem(TimestampedModel):
    """Line item, not independently business-owned — scoped implicitly
    through finished_good."""
    finished_good = models.ForeignKey(FinishedGood, related_name="recipe_items", on_delete=models.CASCADE)
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE)
    qty_per_unit = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        unique_together = ("finished_good", "raw_material")

    def __str__(self):
        return f"{self.qty_per_unit} {self.raw_material.unit} {self.raw_material.name} / {self.finished_good.unit}"
