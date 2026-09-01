import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0002_recipeitem_flexible_usage"),
        ("production", "0006_non_stock_purpose"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderMaterialUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("planned_quantity", models.DecimalField(decimal_places=4, default=0, max_digits=14)),
                ("actual_quantity", models.DecimalField(decimal_places=4, default=0, max_digits=14)),
                ("flexible", models.BooleanField(default=False)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(app_label)s_%(class)s_created", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="material_usages", to="production.order")),
                ("order_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="material_usages", to="production.orderitem")),
                ("raw_material", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inventory.rawmaterial")),
            ],
            options={
                "ordering": ["order_item_id", "raw_material__name"],
            },
        ),
        migrations.AddConstraint(
            model_name="ordermaterialusage",
            constraint=models.UniqueConstraint(fields=("order_item", "raw_material"), name="unique_material_usage_per_order_item"),
        ),
    ]
