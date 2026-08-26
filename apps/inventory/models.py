from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class RawMaterial(BusinessOwnedModel):
    CATEGORY_INGREDIENT = "ingredient"
    CATEGORY_PACKAGING = "packaging"
    CATEGORY_PRODUCTION_SUPPLY = "production_supply"
    CATEGORY_OPERATIONAL_SUPPLY = "operational_supply"

    CATEGORY_CHOICES = [
        (CATEGORY_INGREDIENT, "Ingredient"),
        (CATEGORY_PACKAGING, "Packaging"),
        (CATEGORY_PRODUCTION_SUPPLY, "Production supply (Gas)"),
        (CATEGORY_OPERATIONAL_SUPPLY, "Operational supply (Gloves, Cleaning, etc.)"),
    ]

    name = models.CharField(max_length=120)
    category = models.CharField(
        max_length=24,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_INGREDIENT,
        help_text="Classifies how the material is used. Operational supplies are not tied to a production recipe.",
    )
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
    # Stored in usage units. Higher precision prevents tiny per-gram/per-ml
    # costs from being rounded away when procurement prices are converted.
    cost_per_unit = models.DecimalField(max_digits=16, decimal_places=6, default=0)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["business", "name"], name="unique_raw_material_per_business")]

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.stock is not None and self.reorder_level is not None and self.stock <= self.reorder_level

    @property
    def is_warning(self):
        """Triggers amber warning only for products that have physical-store stock configured."""
        if self.stock is None or self.reorder_level is None or self.is_low:
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
    def reorder_level_purchase_units(self):
        """Stored in usage units, displayed in purchase units."""
        factor = self.total_conversion_factor or Decimal("1")
        return (self.reorder_level / factor).quantize(Decimal("0.01"))

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
    stock = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=None,
        help_text="Physical store (shelf) stock. Leave blank when this product is not stocked in the physical store.")
    total_produced = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text="Cumulative all-time production (customer orders + physical store restocks). "
                   "Never decreases — a running total, not current stock.")
    total_delivered_to_customers = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text="Cumulative units delivered via completed customer orders. Only updates when an "
                   "order is completed — same timing as physical store stock, not when merely ordered.")
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=None,
        help_text="Physical-store reorder threshold in individual units. Leave blank when this product is not stocked in the physical store.")
    # Legacy/default price used when no channel-specific price is configured.
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["business", "name"], name="unique_finished_good_per_business")]

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.stock is not None and self.reorder_level is not None and self.stock <= self.reorder_level

    @property
    def is_warning(self):
        """Triggers amber warning only when physical-store stock is configured."""
        if self.stock is None or self.reorder_level is None or self.is_low:
            return False
        return self.stock <= (self.reorder_level * Decimal("1.5"))

    def selling_price_for(self, channel):
        """Return channel-specific price, falling back to the legacy default."""
        configured = self.channel_prices.filter(channel=channel).first()
        return configured.price if configured else self.selling_price

    @property
    def est_cost(self):
        """Estimated ingredient cost PER UNIT (matches selling_price being
        per unit) — recipe quantities are per batch, so this divides the
        batch cost back down by units_per_batch."""
        batch_cost = Decimal("0")
        for ri in self.recipe_items.select_related("raw_material"):
            batch_cost += ri.raw_material.cost_per_unit * ri.qty_per_batch
        for pm in self.production_materials.select_related("raw_material"):
            batch_cost += pm.raw_material.cost_per_unit * pm.qty_per_batch
        upb = self.units_per_batch or Decimal("1")
        return batch_cost / upb


class FinishedGoodChannelPrice(TimestampedModel):
    CHANNEL_PHYSICAL_STORE = "physical_store"
    CHANNEL_DISTRIBUTION = "distribution"
    CHANNEL_ONLINE = "online"

    CHANNEL_CHOICES = [
        (CHANNEL_PHYSICAL_STORE, "Physical Store"),
        (CHANNEL_DISTRIBUTION, "Distribution"),
        (CHANNEL_ONLINE, "Online"),
    ]

    finished_good = models.ForeignKey(
        FinishedGood, related_name="channel_prices", on_delete=models.CASCADE
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ("finished_good", "channel")
        ordering = ["channel"]

    def __str__(self):
        return f"{self.finished_good.name} — {self.get_channel_display()} — {self.price}"


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


class ProductionMaterial(TimestampedModel):
    """A raw material that is consumed as part of producing a finished good,
    but is not necessarily a recipe ingredient. Examples: cake boxes,
    packaging sleeves, baking gas and other per-batch production supplies.

    Quantities are per BATCH and are always entered in the raw material's
    usage unit, just like RecipeItem.
    """
    finished_good = models.ForeignKey(
        FinishedGood,
        related_name="production_materials",
        on_delete=models.CASCADE,
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        related_name="production_material_links",
        on_delete=models.PROTECT,
    )
    qty_per_batch = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ("finished_good", "raw_material")
        ordering = ["raw_material__name"]

    def __str__(self):
        return f"{self.qty_per_batch} {self.raw_material.usage_unit} {self.raw_material.name} / batch of {self.finished_good.name}"


class StockMovement(BusinessOwnedModel):
    RAW_PURCHASE = "raw_purchase"
    RAW_CONSUMPTION = "raw_consumption"
    FG_PRODUCTION = "fg_production"
    FG_SALE = "fg_sale"
    ADJUSTMENT = "adjustment"

    MOVEMENT_TYPES = [
        (RAW_PURCHASE, "Raw material purchase"),
        (RAW_CONSUMPTION, "Raw material consumption"),
        (FG_PRODUCTION, "Finished goods production"),
        (FG_SALE, "Finished goods sale"),
        (ADJUSTMENT, "Adjustment"),
    ]

    raw_material = models.ForeignKey(
        RawMaterial,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )

    finished_good = models.ForeignKey(
        FinishedGood,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )

    movement_type = models.CharField(
        max_length=30,
        choices=MOVEMENT_TYPES,
    )

    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Signed quantity in the item's internal stock unit.",
    )

    # A finished good can be produced for physical store stock or directly
    # for a customer order. Customer-order production contributes to
    # total_produced but does not change physical shelf stock.
    affects_stock = models.BooleanField(
        default=True,
        help_text="Whether this movement changes the item's physical stock balance.",
    )

    balance_after = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Stock balance immediately after this movement.",
    )

    occurred_at = models.DateTimeField(auto_now_add=True)

    note = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["-occurred_at"]
