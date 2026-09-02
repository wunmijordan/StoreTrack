from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_single_offcut_allocations(apps, schema_editor):
    ProductionBatch = apps.get_model("production", "ProductionBatch")
    Allocation = apps.get_model("production", "ProductionOffcutAllocation")
    for batch in ProductionBatch.objects.filter(
        planned_surplus_customer_units__gt=0,
        planned_surplus_customer__isnull=False,
    ).iterator():
        Allocation.objects.create(
            business_id=batch.business_id,
            created_by_id=batch.created_by_id,
            batch_id=batch.pk,
            customer_id=batch.planned_surplus_customer_id,
            channel=batch.planned_surplus_customer_channel or "distribution",
            quantity=batch.planned_surplus_customer_units,
            sale_id=batch.planned_surplus_sale_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0015_alter_ordernumbersequence_business_and_more"),
        ("sales", "0005_alter_customer_business_alter_customer_created_by_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductionOffcutAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.CharField(choices=[("distribution", "Distribution"), ("online", "Online")], max_length=20)),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=14)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offcut_allocations", to="production.productionbatch")),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_productionoffcutallocation_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_productionoffcutallocation_created", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="planned_offcut_allocations", to="sales.customer")),
                ("sale", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="planned_offcut_allocations", to="sales.sale")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.RunPython(backfill_single_offcut_allocations, migrations.RunPython.noop),
    ]
