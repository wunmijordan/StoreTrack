from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0005_market_stock_lots"),
        ("production", "0018_order_is_market_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionbatch",
            name="excess_market_stock_units",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Additional saleable output from an unassigned Distribution order retained in Market Stock.",
                max_digits=14,
            ),
        ),
    ]
