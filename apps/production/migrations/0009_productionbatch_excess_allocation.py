from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0008_alter_order_customer_payment_method_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionbatch",
            name="excess_stock_units",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="excess_non_stock_units",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="excess_non_stock_purpose",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
