from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_alter_operationalsupplydispense_business_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rawmaterial",
            name="stock",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=13),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="quantity",
            field=models.DecimalField(
                decimal_places=3,
                help_text="Signed quantity in the item's internal stock unit.",
                max_digits=15,
            ),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="balance_after",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Stock balance immediately after this movement. Null for non-stock events.",
                max_digits=15,
                null=True,
            ),
        ),
    ]
