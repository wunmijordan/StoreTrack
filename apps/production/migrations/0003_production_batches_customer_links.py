from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def link_order_customers(apps, schema_editor):
    Customer = apps.get_model("sales", "Customer")
    Order = apps.get_model("production", "Order")
    for order in Order.objects.exclude(customer_name=""):
        name = (order.customer_name or "").strip()
        if not name:
            continue
        customer, _ = Customer.objects.get_or_create(
            business_id=order.business_id,
            name=name,
            defaults={"created_by_id": order.created_by_id, "active": True, "region": order.customer_region or "", "customer_group": order.customer_group or ""},
        )
        if order.customer_id is None:
            order.customer_id = customer.pk
            order.save(update_fields=["customer"])


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0002_customer_payment_status_labels"),
        ("sales", "0002_customer_master"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_orders", to="sales.customer"),
        ),
        migrations.CreateModel(
            name="ProductionBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("production_date", models.DateField()),
                ("batch_number", models.CharField(max_length=60)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                ("planned_units", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("produced_units", models.DecimalField(decimal_places=2, default=0, help_text="Gross units produced before wastage/rejection.", max_digits=14)),
                ("wastage_units", models.DecimalField(decimal_places=2, default=0, help_text="Units lost, rejected or otherwise not saleable.", max_digits=14)),
                ("wastage_reason", models.CharField(blank=True, default="", max_length=255)),
                ("notes", models.TextField(blank=True, default="")),
                ("total_cost", models.DecimalField(decimal_places=4, default=0, max_digits=16)),
                ("unit_cost", models.DecimalField(decimal_places=6, default=0, max_digits=16)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_productionbatch_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_productionbatch_created", to=settings.AUTH_USER_MODEL)),
                ("finished_good", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="production_batches", to="inventory.finishedgood")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="production_batches", to="production.order")),
                ("order_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="production_batches", to="production.orderitem")),
            ],
            options={"ordering": ["-production_date", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="productionbatch",
            constraint=models.UniqueConstraint(fields=("business", "batch_number"), name="unique_production_batch_per_business"),
        ),
        migrations.CreateModel(
            name="ProductionQualityCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("pending", "Pending inspection"), ("passed", "Passed"), ("conditional", "Passed with conditions"), ("failed", "Failed")], default="pending", max_length=12)),
                ("checked_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("defects", models.TextField(blank=True, default="")),
                ("batch", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="quality_check", to="production.productionbatch")),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_productionqualitycheck_set", to="core.business")),
                ("checked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_quality_checks", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_productionqualitycheck_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-checked_at", "-id"]},
        ),
        migrations.AddField(
            model_name="productioncostsnapshot",
            name="production_batch",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cost_snapshots", to="production.productionbatch"),
        ),
        migrations.RunPython(link_order_customers, migrations.RunPython.noop),
    ]
