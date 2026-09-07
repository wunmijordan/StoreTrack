import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction

from core.models import BusinessOwnedModel


class CommerceSettings(BusinessOwnedModel):
    POLICY_REDUCE = "reduce"
    POLICY_REJECT = "reject"
    POLICY_INVITE = "invite_preorder"
    POLICY_SPLIT = "split"
    POLICY_CHOICES = [
        (POLICY_REDUCE, "Reduce to available stock"),
        (POLICY_REJECT, "Reject when stock is insufficient"),
        (POLICY_INVITE, "Invite customer to switch to Pre-order"),
        (POLICY_SPLIT, "Split: fulfil available stock and pre-order the balance"),
    ]

    enabled = models.BooleanField(default=False)
    hosted_storefront_enabled = models.BooleanField(default=True)
    order_now_link_enabled = models.BooleanField(default=True)
    api_enabled = models.BooleanField(default=True)
    connector_enabled = models.BooleanField(default=False)
    insufficient_stock_policy = models.CharField(max_length=20, choices=POLICY_CHOICES, default=POLICY_INVITE)
    public_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name_plural = "commerce settings"
        constraints = [models.UniqueConstraint(fields=["business"], name="one_commerce_settings_per_business")]

    def __str__(self):
        return f"{self.business} commerce"


class CommerceIntegration(BusinessOwnedModel):
    TYPE_API = "api"
    TYPE_WEBHOOK = "webhook"
    TYPE_CHOICES = [(TYPE_API, "Headless API"), (TYPE_WEBHOOK, "Platform webhook / connector")]

    name = models.CharField(max_length=100)
    integration_type = models.CharField(max_length=12, choices=TYPE_CHOICES, default=TYPE_API)
    api_key = models.CharField(max_length=80, unique=True, editable=False)
    webhook_secret = models.CharField(max_length=80, blank=True, default="")
    active = models.BooleanField(default=True)
    allowed_origin = models.CharField(max_length=255, blank=True, default="")

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = secrets.token_urlsafe(32)
        if self.integration_type == self.TYPE_WEBHOOK and not self.webhook_secret:
            self.webhook_secret = secrets.token_urlsafe(32)
        return super().save(*args, **kwargs)


class StorefrontProduct(BusinessOwnedModel):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    finished_good = models.OneToOneField("inventory.FinishedGood", on_delete=models.CASCADE, related_name="storefront_product")
    published = models.BooleanField(default=False)
    public_name = models.CharField(max_length=140, blank=True, default="")
    description = models.TextField(blank=True, default="")
    image_url = models.URLField(blank=True, default="")
    allow_stock_order = models.BooleanField(default=True)
    allow_preorder = models.BooleanField(default=True)
    allow_online_order = models.BooleanField(default=True)
    allow_distribution_order = models.BooleanField(default=True)
    min_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    max_quantity = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    preorder_min_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    distribution_min_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    preorder_lead_time = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        ordering = ["finished_good__name"]

    @property
    def display_name(self):
        return self.public_name.strip() or self.finished_good.name

    @property
    def available_now(self):
        return Decimal(self.finished_good.physical_saleable_stock or 0)

    @property
    def stock_price(self):
        return self.finished_good.selling_price_for("physical_store")

    @property
    def preorder_price(self):
        return self.finished_good.selling_price_for("online")

    @property
    def distribution_price(self):
        return self.finished_good.selling_price_for("distribution")

    def __str__(self):
        return self.display_name


class CommerceIntake(BusinessOwnedModel):
    SOURCE_STOREFRONT = "storefront"
    SOURCE_API = "api"
    SOURCE_CONNECTOR = "connector"
    SOURCE_CHOICES = [(SOURCE_STOREFRONT, "Hosted storefront"), (SOURCE_API, "API"), (SOURCE_CONNECTOR, "External connector")]
    MODE_STOCK = "stock"
    MODE_PREORDER = "preorder"
    MODE_CHOICES = [(MODE_STOCK, "Order"), (MODE_PREORDER, "Pre-order")]
    CHANNEL_PHYSICAL_STORE = "physical_store"
    CHANNEL_ONLINE = "online"
    CHANNEL_DISTRIBUTION = "distribution"
    CHANNEL_CHOICES = [
        (CHANNEL_PHYSICAL_STORE, "Physical Store"),
        (CHANNEL_ONLINE, "Online"),
        (CHANNEL_DISTRIBUTION, "Distribution / Bulk"),
    ]
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_AWAITING_PREORDER = "awaiting_preorder"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_FULFILLED = "fulfilled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending review"), (STATUS_ACCEPTED, "Accepted"),
        (STATUS_AWAITING_PREORDER, "Awaiting Pre-order confirmation"),
        (STATUS_REJECTED, "Rejected"), (STATUS_CANCELLED, "Cancelled"), (STATUS_FULFILLED, "Fulfilled"),
    ]
    PAYMENT_PENDING = "pending"
    PAYMENT_CONFIRMED = "confirmed"
    PAYMENT_FAILED = "failed"
    PAYMENT_CHOICES = [(PAYMENT_PENDING, "Pending"), (PAYMENT_CONFIRMED, "Confirmed"), (PAYMENT_FAILED, "Failed")]
    FULFIL_PENDING = "pending"
    FULFIL_PARTIAL = "partial"
    FULFIL_COMPLETE = "complete"
    FULFIL_CHOICES = [(FULFIL_PENDING, "Pending"), (FULFIL_PARTIAL, "Partial"), (FULFIL_COMPLETE, "Complete")]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    public_number = models.CharField(max_length=40, blank=True, default="")
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default=SOURCE_STOREFRONT)
    external_order_id = models.CharField(max_length=120, blank=True, default="")
    idempotency_key = models.CharField(max_length=120, blank=True, default="")
    ordering_mode = models.CharField(max_length=12, choices=MODE_CHOICES)
    sales_channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_PHYSICAL_STORE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=40, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")
    customer_address = models.TextField(blank=True, default="")
    service_mode = models.CharField(max_length=20, blank=True, default="")
    table_reference = models.CharField(max_length=40, blank=True, default="")
    payment_state = models.CharField(max_length=12, choices=PAYMENT_CHOICES, default=PAYMENT_PENDING)
    fulfilment_state = models.CharField(max_length=12, choices=FULFIL_CHOICES, default=FULFIL_PENDING)
    accepted_order = models.ForeignKey("production.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="commerce_intakes")
    accepted_sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="commerce_intakes")
    split_order = models.ForeignKey("production.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="split_commerce_intakes")
    rejection_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "public_number"],
                condition=~models.Q(public_number=""),
                name="unique_commerce_number_per_business",
            ),
            models.UniqueConstraint(
                fields=["business", "source", "external_order_id"],
                condition=~models.Q(external_order_id=""),
                name="unique_external_commerce_order",
            ),
            models.UniqueConstraint(
                fields=["business", "source", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_commerce_idempotency_key",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.public_number:
            return super().save(*args, **kwargs)
        if not self.business_id:
            raise ValueError("Commerce intake business must be set before allocating an order number.")
        with transaction.atomic():
            sequence, _ = CommerceOrderNumberSequence.raw_objects.select_for_update().get_or_create(
                business_id=self.business_id,
                defaults={"next_number": 1, "created_by_id": self.created_by_id},
            )
            self.public_number = f"WEB-{sequence.next_number:06d}"
            sequence.next_number += 1
            sequence.save(update_fields=["next_number", "updated_at"])
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"public_number"}
            return super().save(*args, **kwargs)

    @property
    def total(self):
        return sum((row.line_total for row in self.items.all()), Decimal("0"))

    @property
    def display_sales_channel(self):
        from core.verticals import vertical_config
        return vertical_config(self.business)["commerce_channels"].get(
            self.sales_channel, self.get_sales_channel_display()
        )


class CommerceOrderNumberSequence(BusinessOwnedModel):
    """Locked per-business sequence for human-facing commerce order numbers."""

    next_number = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business"], name="unique_commerce_order_sequence_per_business"),
        ]


class CommerceIntakeItem(models.Model):
    intake = models.ForeignKey(CommerceIntake, on_delete=models.CASCADE, related_name="items")
    storefront_product = models.ForeignKey(StorefrontProduct, on_delete=models.PROTECT)
    finished_good = models.ForeignKey("inventory.FinishedGood", on_delete=models.PROTECT)
    requested_quantity = models.DecimalField(max_digits=14, decimal_places=2)
    accepted_stock_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    production_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    @property
    def line_total(self):
        return self.requested_quantity * self.unit_price


class CommercePaymentConfiguration(BusinessOwnedModel):
    """Tenant-owned payment credentials and settlement destinations.

    Provider secrets are intentionally never serialized by the public API. The
    form also treats a blank submitted secret as "keep the existing value".
    """

    currency = models.CharField(max_length=3, default="NGN")
    paystack_enabled = models.BooleanField(default=False)
    paystack_secret_key = models.CharField(max_length=255, blank=True, default="")
    paystack_account = models.ForeignKey(
        "core.CashAccount", null=True, blank=True, on_delete=models.PROTECT,
        related_name="commerce_paystack_configurations",
    )
    monnify_enabled = models.BooleanField(default=False)
    monnify_api_key = models.CharField(max_length=255, blank=True, default="")
    monnify_secret_key = models.CharField(max_length=255, blank=True, default="")
    monnify_contract_code = models.CharField(max_length=80, blank=True, default="")
    monnify_base_url = models.URLField(default="https://api.monnify.com")
    monnify_account = models.ForeignKey(
        "core.CashAccount", null=True, blank=True, on_delete=models.PROTECT,
        related_name="commerce_monnify_configurations",
    )
    bank_transfer_enabled = models.BooleanField(default=False)
    bank_name = models.CharField(max_length=120, blank=True, default="")
    bank_account_name = models.CharField(max_length=160, blank=True, default="")
    bank_account_number = models.CharField(max_length=40, blank=True, default="")
    bank_instructions = models.CharField(max_length=255, blank=True, default="")
    bank_cash_account = models.ForeignKey(
        "core.CashAccount", null=True, blank=True, on_delete=models.PROTECT,
        related_name="commerce_bank_transfer_configurations",
    )
    cash_enabled = models.BooleanField(default=False)
    cash_instructions = models.CharField(max_length=255, blank=True, default="")
    cash_account = models.ForeignKey(
        "core.CashAccount", null=True, blank=True, on_delete=models.PROTECT,
        related_name="commerce_cash_configurations",
    )

    class Meta:
        verbose_name = "commerce payment configuration"
        constraints = [
            models.UniqueConstraint(fields=["business"], name="one_commerce_payment_config_per_business"),
        ]


class CommercePayment(BusinessOwnedModel):
    METHOD_PAYSTACK = "paystack"
    METHOD_MONNIFY = "monnify"
    METHOD_BANK_TRANSFER = "bank_transfer"
    METHOD_CASH = "cash"
    METHOD_CHOICES = [
        (METHOD_PAYSTACK, "Paystack"),
        (METHOD_MONNIFY, "Monnify"),
        (METHOD_BANK_TRANSFER, "Bank transfer"),
        (METHOD_CASH, "Cash"),
    ]

    STATUS_PENDING = "pending"
    STATUS_AWAITING_CUSTOMER = "awaiting_customer"
    STATUS_AWAITING_VERIFICATION = "awaiting_verification"
    STATUS_PARTIALLY_PAID = "partially_paid"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_AWAITING_CUSTOMER, "Awaiting customer"),
        (STATUS_AWAITING_VERIFICATION, "Awaiting verification"),
        (STATUS_PARTIALLY_PAID, "Partially paid"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REFUNDED, "Refunded"),
    ]
    ACTIVE_STATUSES = {
        STATUS_PENDING, STATUS_AWAITING_CUSTOMER,
        STATUS_AWAITING_VERIFICATION, STATUS_PARTIALLY_PAID,
    }

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    intake = models.ForeignKey(CommerceIntake, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING)
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    amount_paid = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="NGN")
    reference = models.CharField(max_length=80, unique=True)
    gateway_reference = models.CharField(max_length=160, blank=True, default="")
    authorization_url = models.URLField(max_length=500, blank=True, default="")
    instructions = models.CharField(max_length=500, blank=True, default="")
    idempotency_key = models.CharField(max_length=160)
    return_url = models.URLField(max_length=500, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="verified_commerce_payments",
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    gateway_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "intake", "idempotency_key"],
                name="unique_commerce_payment_idempotency",
            ),
        ]

    @property
    def balance(self):
        return max(Decimal("0"), Decimal(self.amount or 0) - Decimal(self.amount_paid or 0))


class CommercePaymentClaim(BusinessOwnedModel):
    STATUS_SUBMITTED = "submitted"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Awaiting verification"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    payment = models.ForeignKey(CommercePayment, on_delete=models.PROTECT, related_name="claims")
    payer_name = models.CharField(max_length=160)
    transfer_reference = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="reviewed_commerce_payment_claims",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    confirmed_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True, default="")
    mismatch_reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "transfer_reference"],
                name="unique_commerce_transfer_reference",
            ),
        ]


class CommercePaymentReceipt(BusinessOwnedModel):
    payment = models.ForeignKey(CommercePayment, on_delete=models.PROTECT, related_name="receipts")
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    external_reference = models.CharField(max_length=160, blank=True, default="")
    idempotency_key = models.CharField(max_length=180)
    account = models.ForeignKey(
        "core.CashAccount", on_delete=models.PROTECT, related_name="commerce_payment_receipts",
    )
    financial_transaction = models.OneToOneField(
        "core.FinancialTransaction", on_delete=models.PROTECT, related_name="commerce_payment_receipt",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="commerce_payment_receipts",
    )
    verified_at = models.DateTimeField()
    location = models.CharField(max_length=120, blank=True, default="")
    note = models.CharField(max_length=500, blank=True, default="")
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="reversed_commerce_payment_receipts",
    )
    reversal_reason = models.CharField(max_length=500, blank=True, default="")
    reversal_transaction = models.OneToOneField(
        "core.FinancialTransaction", null=True, blank=True, on_delete=models.PROTECT,
        related_name="commerce_payment_receipt_reversal",
    )

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "payment", "idempotency_key"],
                name="unique_commerce_receipt_idempotency",
            ),
            models.UniqueConstraint(
                fields=["business", "external_reference"],
                condition=~models.Q(external_reference=""),
                name="unique_settled_commerce_external_ref",
            ),
        ]


class CommercePaymentAllocation(models.Model):
    receipt = models.ForeignKey(CommercePaymentReceipt, on_delete=models.PROTECT, related_name="allocations")
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, related_name="commerce_payment_allocations")
    customer_payment = models.OneToOneField(
        "sales.CustomerPayment", on_delete=models.PROTECT, related_name="commerce_payment_allocation",
    )
    reversal_customer_payment = models.OneToOneField(
        "sales.CustomerPayment", null=True, blank=True, on_delete=models.PROTECT,
        related_name="commerce_payment_reversal_allocation",
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["receipt", "sale"], name="unique_commerce_receipt_sale_allocation"),
        ]


class CommerceGatewayEvent(BusinessOwnedModel):
    PROVIDER_PAYSTACK = CommercePayment.METHOD_PAYSTACK
    PROVIDER_MONNIFY = CommercePayment.METHOD_MONNIFY
    PROVIDER_CHOICES = [
        (PROVIDER_PAYSTACK, "Paystack"),
        (PROVIDER_MONNIFY, "Monnify"),
    ]

    payment = models.ForeignKey(
        CommercePayment, null=True, blank=True, on_delete=models.PROTECT, related_name="gateway_events",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    event_key = models.CharField(max_length=160)
    event_type = models.CharField(max_length=100, blank=True, default="")
    signature_valid = models.BooleanField(default=False)
    provider_verified = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["business", "provider", "event_key"], name="unique_commerce_gateway_event"),
        ]
