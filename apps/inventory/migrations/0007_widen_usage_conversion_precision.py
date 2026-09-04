from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0006_stock_product_purchase_movement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rawmaterial",
            name="usage_conversion_factor",
            field=models.DecimalField(
                decimal_places=6,
                default=1,
                help_text=(
                    "How many usage units in ONE package_unit. Standard: kg→g is 1000, litre→ml is 1000, "
                    "same unit both ways is 1. Non-standard (spoon, cap…): count it yourself, e.g. "
                    "'my spoon holds 5g' → if package_unit is kg, that's 200 spoons per kg → 200."
                ),
                max_digits=16,
            ),
        ),
    ]
