from decimal import Decimal
from django.conf import settings
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
        ("completed", "Completed"), ("rejected", "Rejected"), ("reversed", "Reversed"),
    ]
    PAYMENT_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]
    TRANSACTION_CHOICES = [("paid", "Paid"), ("unpaid", "Unpaid")]
    DESTINATION_CHOICES = [
        ("store", "Store replenishment — add to Physical Store stock"),
        ("non_stock", "Non-stock purpose — do not add to Physical Store stock"),
    ]
    CUSTOMER_PAYMENT_CHOICES = [("paid", "Received"), ("unpaid", "Receivable")]

    date = models.DateField()
    order_type = models.CharField(max_length=15, choices=TYPE_CHOICES, default="physical_store")
    production_destination = models.CharField(
        max_length=12, choices=DESTINATION_CHOICES, default="store",
        help_text="Physical Store orders only: choose whether completed production enters Shelf Stock or is for a non-stock purpose.",
    )
    non_stock_purpose = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Specific purpose when production is not going to Physical Store stock (e.g. Staff Welfare, Gift, Charity).",
    )
    customer = models.ForeignKey("sales.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="production_orders")
    customer_name = models.CharField(max_length=120, blank=True,
        help_text="Required for distribution and online orders; leave blank for a physical store restock.")
    customer_region = models.CharField(max_length=100, blank=True,
        help_text="Optional reporting region/territory for distribution or online customer analytics.")
    customer_group = models.CharField(max_length=100, blank=True,
        help_text="Optional customer group/segment for distribution or online customer analytics.")
    # Legacy payment fields are retained for historical rows and database
    # compatibility. They are deliberately not exposed for Physical Store
    # Orders: those are production/restock requests, not direct sales.
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_CHOICES, default="paid", help_text="Legacy field retained for historical physical-store orders; direct sales are recorded in Sales.")
    customer_payment_status = models.CharField(max_length=10, choices=CUSTOMER_PAYMENT_CHOICES, default="paid", help_text="Distribution/Online only: whether the customer payment has been received or remains a receivable.")
    customer_payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Transfer", blank=True)
    customer_payment_account = models.ForeignKey("core.CashAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="customer_order_payments")
    unpaid_description = models.CharField(max_length=255, blank=True, default="")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Cash", blank=True,
        help_text="Legacy field retained for historical rows; customer-order payment is handled through Finance.")
    account = models.ForeignKey("core.CashAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="production_orders")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True)
    approved_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_reason = models.CharField(max_length=255, blank=True, default="")
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reversed_production_orders")

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
            production_batches = item.effective_production_batch_qty
            production_pieces = item.effective_production_piece_qty
            per_piece_factor = production_pieces / upb

            links = list(good.recipe_items.select_related("raw_material"))
            links += list(good.production_materials.select_related("raw_material"))

            for link in links:
                qty = link.qty_per_batch * production_batches
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
    production_batch_qty = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, blank=True,
        help_text="Optional production plan. Leave 0/blank to produce exactly the ordered quantity.",
    )
    production_piece_qty = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, blank=True,
        help_text="Optional loose pieces in the production plan. Leave 0/blank to produce exactly the ordered quantity.",
    )
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
    def has_explicit_production_plan(self):
        return (self.production_batch_qty or Decimal("0")) > 0 or (self.production_piece_qty or Decimal("0")) > 0

    @property
    def effective_production_batch_qty(self):
        return self.production_batch_qty if self.has_explicit_production_plan else self.batch_qty

    @property
    def effective_production_piece_qty(self):
        return self.production_piece_qty if self.has_explicit_production_plan else self.piece_qty

    @property
    def production_total_units(self):
        upb = self.finished_good.units_per_batch or Decimal("1")
        return self.effective_production_batch_qty * upb + self.effective_production_piece_qty

    @property
    def planned_overproduction_units(self):
        return max(Decimal("0"), self.production_total_units - self.total_units)

    @property
    def line_total(self):
        """Discount is applied PER UNIT, not once on the line total — e.g.
        50 units at 1500 with a 200 discount is (1500-200)*50 = 65,000,
        not 1500*50-200. Matches how a per-item price cut actually works."""
        return self.total_units * ((self.price or Decimal("0")) - (self.discount or Decimal("0")))
class OrderMaterialUsage(BusinessOwnedModel):
    """Actual raw-material quantity released for one production order item.

    Created at approval so flexible recipe ingredients can vary from the base
    recipe while preserving the quantity used for stock release and costing.
    """
    order = models.ForeignKey(Order, related_name="material_usages", on_delete=models.CASCADE)
    order_item = models.ForeignKey(OrderItem, related_name="material_usages", on_delete=models.CASCADE)
    raw_material = models.ForeignKey("inventory.RawMaterial", on_delete=models.PROTECT)
    planned_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    actual_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    flexible = models.BooleanField(default=False)

    class Meta:
        ordering = ["order_item_id", "raw_material__name"]
        constraints = [
            models.UniqueConstraint(fields=["order_item", "raw_material"], name="unique_material_usage_per_order_item")
        ]

    def __str__(self):
        return f"Order #{self.order_id} — {self.raw_material.name}: {self.actual_quantity}"


class ProductionBatch(BusinessOwnedModel):
    """A traceable production output record for one finished-good order line.

    The batch records planned output, gross production, wastage and saleable
    output. It is the bridge between the production event, its frozen cost,
    quality inspection and any customer/shelf movement that follows.
    """
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="production_batches")
    order_item = models.ForeignKey(OrderItem, on_delete=models.PROTECT, related_name="production_batches")
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT, related_name="production_batches")
    production_date = models.DateField()
    batch_number = models.CharField(max_length=60)
    expiry_date = models.DateField(null=True, blank=True)
    planned_units = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ordered_units = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Customer/requested quantity kept separately from the production target.",
    )
    planned_surplus_stock_units = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Saleable planned overproduction retained as general Physical Store stock.",
    )
    planned_surplus_customer_units = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    planned_surplus_customer = models.ForeignKey("sales.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="planned_offcut_batches")
    planned_surplus_customer_channel = models.CharField(max_length=20, blank=True, default="")
    planned_surplus_sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="planned_offcut_batches")
    is_reversed = models.BooleanField(default=False)
    produced_units = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Gross units produced before wastage/rejection.")
    wastage_units = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Units lost, rejected or otherwise not saleable.")
    wastage_reason = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    total_cost = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    unit_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0)

    # A customer order is fulfilled at the ordered quantity. If gross
    # production is sufficient but wastage/rejection leaves fewer saleable
    # units, the deficit is recorded explicitly rather than pretending the
    # order was produced short. Reconciliation is a separate auditable
    # allocation from available surplus production of the same product, regardless of channel.
    shortage_flag = models.BooleanField(default=False)
    shortage_reason = models.CharField(max_length=255, blank=True, default="")

    # Saleable output above planned units must be explicitly accounted for.
    # Excess assigned to shelf stock remains available for later shortage
    # reconciliation; excess assigned to a non-stock purpose is consumed by
    # that purpose and is not available to satisfy another order.
    excess_stock_units = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    excess_non_stock_units = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    excess_non_stock_purpose = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-production_date", "-id"]
        constraints = [models.UniqueConstraint(fields=["business", "batch_number"], name="unique_production_batch_per_business")]

    def __str__(self):
        return f"{self.batch_number} — {self.finished_good.name}"

    @property
    def saleable_units(self):
        return max(Decimal("0"), self.produced_units - self.wastage_units)

    @property
    def yield_percent(self):
        if not self.planned_units:
            return Decimal("0")
        return (self.saleable_units / self.planned_units * Decimal("100")).quantize(Decimal("0.01"))

    @property
    def shortage_units(self):
        required = self.ordered_units or self.planned_units
        return max(Decimal("0"), required - self.saleable_units)

    @property
    def reconciled_units(self):
        return sum((r.quantity for r in self.reconciliation_in.all()), Decimal("0"))

    @property
    def outstanding_shortage_units(self):
        return max(Decimal("0"), self.shortage_units - self.reconciled_units)

    @property
    def excess_units(self):
        """Unplanned saleable output above the explicit production target."""
        return max(Decimal("0"), self.saleable_units - self.planned_units)

    @property
    def total_surplus_units(self):
        """All saleable output above the customer/requested quantity."""
        required = self.ordered_units or self.planned_units
        return max(Decimal("0"), self.saleable_units - required)

    @property
    def available_surplus_units(self):
        """Excess units deliberately retained in shelf stock and still
        available to satisfy a shortage from any production channel."""
        outgoing = sum((r.quantity for r in self.reconciliation_out.all()), Decimal("0"))
        retained = max(Decimal("0"), self.planned_surplus_stock_units + self.excess_stock_units - outgoing)
        physical_stock = max(Decimal("0"), Decimal(self.finished_good.stock or 0))
        return min(retained, physical_stock)


class ProductionBatchReconciliation(BusinessOwnedModel):
    """Auditable fulfillment allocation from surplus production to a
    customer-order production shortage. It is not a new sale, cash entry, or production event.
    When the source surplus sits in shelf stock, reconciliation removes the
    allocated quantity from physical stock."""

    source_batch = models.ForeignKey(
        "ProductionBatch",
        on_delete=models.PROTECT,
        related_name="reconciliation_out",
    )
    target_batch = models.ForeignKey(
        "ProductionBatch",
        on_delete=models.PROTECT,
        related_name="reconciliation_in",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.quantity} — {self.source_batch.batch_number} → {self.target_batch.batch_number}"


class ProductionQualityCheck(BusinessOwnedModel):
    """Quality inspection attached to a completed production batch."""
    STATUS_CHOICES = [
        ("pending", "Pending inspection"),
        ("passed", "Passed"),
        ("conditional", "Passed with conditions"),
        ("failed", "Failed"),
    ]
    batch = models.OneToOneField(ProductionBatch, on_delete=models.CASCADE, related_name="quality_check")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="production_quality_checks")
    checked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    defects = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-checked_at", "-id"]

    def __str__(self):
        return f"QC — {self.batch.batch_number} — {self.get_status_display()}"


class ProductionCostSnapshot(BusinessOwnedModel):
    """Frozen production cost calculated when an order is completed.

    Each raw-material line uses the latest received procurement cost available
    on the production date. Older procurement prices are never averaged in.
    """
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_snapshots")
    order_item = models.ForeignKey(OrderItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_snapshots")
    production_batch = models.ForeignKey("ProductionBatch", null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_snapshots")
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT, related_name="production_cost_snapshots")
    production_date = models.DateField()
    produced_units = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    unit_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0)
    cost_source = models.CharField(max_length=40, default="latest_procurement")
    batch_number = models.CharField(max_length=40, blank=True, default="")
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-production_date", "-id"]

    def __str__(self):
        return f"{self.finished_good.name} — {self.unit_cost} / unit — {self.production_date}"


class ProductionCostLine(TimestampedModel):
    snapshot = models.ForeignKey(ProductionCostSnapshot, related_name="lines", on_delete=models.CASCADE)
    raw_material = models.ForeignKey("inventory.RawMaterial", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    usage_unit_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0)
    total_cost = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    source = models.CharField(max_length=20, default="latest_procurement")

    def __str__(self):
        return f"{self.snapshot.finished_good.name} — {self.raw_material.name}"
