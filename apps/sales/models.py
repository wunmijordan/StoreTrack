from decimal import Decimal
from django.db import models
from core.models import BusinessOwnedModel, TimestampedModel


class Sale(BusinessOwnedModel):
    """A completed stock/sales event. Physical-store rows may be paid or
    unpaid product issues; Distribution/Online rows may remain receivables
    until Finance records one or more CustomerPayment entries."""

    PAYMENT_CHOICES = [("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")]
    TRANSACTION_CHOICES = [("paid", "Paid"), ("partial", "Partially Paid"), ("unpaid", "Unpaid")]
    SOURCE_CHOICES = [("walkin", "Physical Store"), ("distribution_order", "Distribution Order"), ("online_order", "Online Order")]

    date = models.DateField()
    customer = models.CharField(max_length=120, blank=True, default="Walk-in")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_CHOICES, default="paid", help_text="Payment state. Physical-store unpaid sales are non-cash issues; customer-order sales are receivables until Finance records payment.")
    unpaid_description = models.CharField(max_length=255, blank=True, default="", help_text="Reason for physical-store unpaid issue, or receivable note for customer orders.")
    account = models.ForeignKey("core.CashAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="Cash")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="walkin")
    linked_order = models.ForeignKey(
        "production.Order", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Set automatically if this sale was created from a completed distribution or online order.",
    )

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Sale #{self.id} — {self.customer}"

    @property
    def total(self):
        return sum((i.line_total for i in self.items.all()), Decimal("0"))


class SaleItem(TimestampedModel):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    batch_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    piece_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0,
        help_text="Snapshot of the product's selling price at sale time — set automatically.")
    unit_cost = models.DecimalField(max_digits=16, decimal_places=6, null=True, blank=True,
        help_text="Historical finished-good cost per unit at the time of sale.")

    def __str__(self):
        return f"{self.sale.customer} — {self.finished_good.name} x{self.total_units}"

    @property
    def total_units(self):
        upb = self.finished_good.units_per_batch or Decimal("1")
        return self.batch_qty * upb + self.piece_qty

    @property
    def line_total(self):
        """Discount is applied PER UNIT, not once on the line total — e.g.
        50 units at 1500 with a 200 discount is (1500-200)*50 = 65,000,
        not 1500*50-200."""
        return self.total_units * ((self.price or Decimal("0")) - (self.discount or Decimal("0")))

class CustomerPayment(BusinessOwnedModel):
    date = models.DateField()
    customer = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=Sale.PAYMENT_CHOICES, default="Cash")
    reference = models.CharField(max_length=80, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    sale = models.ForeignKey(Sale, null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    account = models.ForeignKey("core.CashAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="customer_payments")
    class Meta: ordering = ["-date", "-id"]
