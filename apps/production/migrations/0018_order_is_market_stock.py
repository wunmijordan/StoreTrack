from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0017_alter_productionoffcutallocation_business_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="is_market_stock",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Distribution orders only: produce without assigning a customer and retain "
                    "the completed goods as available stock for future sales."
                ),
            ),
        ),
    ]
