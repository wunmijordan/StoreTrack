# Generated for the additive pre-intake checkout/payment boundary.

import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0006_storefrontproduct_image"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="commercesettings",
            name="checkout_reservation_minutes",
            field=models.PositiveSmallIntegerField(
                default=15,
                validators=[django.core.validators.MinValueValidator(5), django.core.validators.MaxValueValidator(120)],
                help_text="How long Physical Store stock is held while a customer completes payment.",
            ),
        ),
        migrations.CreateModel(
            name="CommerceCheckoutSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("source", models.CharField(choices=[("storefront", "Hosted storefront"), ("api", "API"), ("connector", "External connector")], default="api", max_length=12)),
                ("external_order_id", models.CharField(blank=True, default="", max_length=120)),
                ("idempotency_key", models.CharField(max_length=120)),
                ("ordering_mode", models.CharField(choices=[("stock", "Order"), ("preorder", "Pre-order")], max_length=12)),
                ("sales_channel", models.CharField(choices=[("physical_store", "Physical Store"), ("online", "Online"), ("distribution", "Distribution / Bulk")], max_length=20)),
                ("customer_name", models.CharField(max_length=160)),
                ("customer_phone", models.CharField(blank=True, default="", max_length=40)),
                ("customer_email", models.EmailField(blank=True, default="", max_length=254)),
                ("customer_address", models.TextField(blank=True, default="")),
                ("service_mode", models.CharField(blank=True, default="", max_length=20)),
                ("table_reference", models.CharField(blank=True, default="", max_length=40)),
                ("currency", models.CharField(default="NGN", max_length=3)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("status", models.CharField(choices=[("awaiting_payment", "Awaiting payment"), ("paid", "Paid — creating order"), ("materialized", "Order created"), ("paid_review", "Paid — needs fulfilment review"), ("expired", "Expired"), ("cancelled", "Cancelled")], default="awaiting_payment", max_length=24)),
                ("reservation_expires_at", models.DateTimeField(blank=True, null=True)),
                ("reservation_released_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("materialization_error", models.CharField(blank=True, default="", max_length=500)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(app_label)s_%(class)s_created", to=settings.AUTH_USER_MODEL)),
                ("materialized_intake", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="checkout_session", to="commerce.commerceintake")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="CommerceCheckoutItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requested_quantity", models.DecimalField(decimal_places=2, max_digits=14)),
                ("payable_quantity", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reserved_stock_quantity", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("production_quantity", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("checkout", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="commerce.commercecheckoutsession")),
                ("finished_good", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inventory.finishedgood")),
                ("storefront_product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="commerce.storefrontproduct")),
            ],
        ),
        migrations.AddConstraint(
            model_name="commercecheckoutsession",
            constraint=models.UniqueConstraint(fields=("business", "source", "idempotency_key"), name="unique_checkout_idempotency_key"),
        ),
        migrations.AddConstraint(
            model_name="commercecheckoutsession",
            constraint=models.UniqueConstraint(condition=~models.Q(external_order_id=""), fields=("business", "source", "external_order_id"), name="unique_checkout_external_order"),
        ),
        migrations.AddIndex(
            model_name="commercecheckoutsession",
            index=models.Index(fields=["business", "status", "reservation_expires_at"], name="commerce_checkout_res_idx"),
        ),
        migrations.AddIndex(
            model_name="commercecheckoutitem",
            index=models.Index(fields=["finished_good", "reserved_stock_quantity"], name="commerce_checkout_good_idx"),
        ),
        migrations.RemoveConstraint(
            model_name="commercepayment",
            name="unique_commerce_payment_idempotency",
        ),
        migrations.AlterField(
            model_name="commercepayment",
            name="intake",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="commerce.commerceintake"),
        ),
        migrations.AddField(
            model_name="commercepayment",
            name="checkout",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="commerce.commercecheckoutsession"),
        ),
        migrations.AddConstraint(
            model_name="commercepayment",
            constraint=models.UniqueConstraint(condition=models.Q(intake__isnull=False), fields=("business", "intake", "idempotency_key"), name="unique_commerce_payment_idempotency"),
        ),
        migrations.AddConstraint(
            model_name="commercepayment",
            constraint=models.UniqueConstraint(condition=models.Q(checkout__isnull=False), fields=("business", "checkout", "idempotency_key"), name="unique_checkout_payment_idempotency"),
        ),
        migrations.AddConstraint(
            model_name="commercepayment",
            constraint=models.CheckConstraint(condition=(models.Q(intake__isnull=False, checkout__isnull=True) | models.Q(intake__isnull=True, checkout__isnull=False)), name="commerce_payment_has_one_target"),
        ),
    ]
