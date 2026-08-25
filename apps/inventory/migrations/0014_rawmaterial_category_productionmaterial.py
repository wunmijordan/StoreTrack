import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0013_stockmovement_affects_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="rawmaterial",
            name="category",
            field=models.CharField(
                choices=[
                    ("ingredient", "Ingredient"),
                    ("packaging", "Packaging"),
                    ("production_supply", "Production supply (gas, fuel, etc.)"),
                    ("operational_supply", "Operational supply (gloves, cleaning, etc.)"),
                ],
                default="ingredient",
                help_text="Classifies how the material is used. Operational supplies are not tied to a production recipe.",
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="ProductionMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("qty_per_batch", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("finished_good", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_materials", to="inventory.finishedgood")),
                ("raw_material", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="production_material_links", to="inventory.rawmaterial")),
            ],
            options={
                "ordering": ["raw_material__name"],
                "unique_together": {("finished_good", "raw_material")},
            },
        ),
    ]
