from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0009_productionbatch_excess_allocation"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="production_batch_qty",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="Optional production plan. Leave 0/blank to produce exactly the ordered quantity.",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="production_piece_qty",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="Optional loose pieces in the production plan. Leave 0/blank to produce exactly the ordered quantity.",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="ordered_units",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Customer/requested quantity kept separately from the production target.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="planned_surplus_stock_units",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Saleable planned overproduction retained as general Physical Store stock.",
                max_digits=14,
            ),
        ),
    ]
