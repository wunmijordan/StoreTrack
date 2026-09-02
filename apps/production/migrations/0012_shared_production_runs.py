from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0004_rawmaterial_stock_3dp"),
        ("production", "0011_order_reversal_offcut_customer"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductionRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField()),
                ("run_number", models.CharField(max_length=60)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("approved", "Approved / in production"), ("completed", "Completed")], default="draft", max_length=12)),
                ("notes", models.TextField(blank=True, default="")),
                ("approved_date", models.DateField(blank=True, null=True)),
                ("completed_date", models.DateField(blank=True, null=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_productionrun_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_productionrun_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.CreateModel(
            name="ProductionRunOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_run_links", to="production.order")),
                ("production_run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="order_links", to="production.productionrun")),
            ],
            options={"ordering": ["order_id"]},
        ),
        migrations.CreateModel(
            name="ProductionRunMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("planned_quantity", models.DecimalField(decimal_places=4, default=0, max_digits=14)),
                ("actual_quantity", models.DecimalField(decimal_places=4, default=0, max_digits=14)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_productionrunmaterial_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_productionrunmaterial_created", to=settings.AUTH_USER_MODEL)),
                ("production_run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shared_materials", to="production.productionrun")),
                ("raw_material", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shared_production_runs", to="inventory.rawmaterial")),
            ],
            options={"ordering": ["raw_material__name"]},
        ),
        migrations.AddField(
            model_name="productionrun",
            name="orders",
            field=models.ManyToManyField(related_name="production_runs", through="production.ProductionRunOrder", to="production.order"),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="production_run",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_batches", to="production.productionrun"),
        ),
        migrations.AddConstraint(
            model_name="productionrun",
            constraint=models.UniqueConstraint(fields=("business", "run_number"), name="unique_production_run_number_per_business"),
        ),
        migrations.AddConstraint(
            model_name="productionrunorder",
            constraint=models.UniqueConstraint(fields=("order",), name="order_in_at_most_one_production_run"),
        ),
        migrations.AddConstraint(
            model_name="productionrunmaterial",
            constraint=models.UniqueConstraint(fields=("production_run", "raw_material"), name="unique_shared_material_per_production_run"),
        ),
    ]
