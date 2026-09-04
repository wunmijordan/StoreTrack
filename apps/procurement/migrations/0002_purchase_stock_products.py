from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0007_widen_usage_conversion_precision"),
        ("procurement", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="purchaseorderitem",
            name="raw_material",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchase_order_items",
                to="inventory.rawmaterial",
            ),
        ),
        migrations.AddField(
            model_name="purchaseorderitem",
            name="finished_good",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchase_order_items",
                to="inventory.finishedgood",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchaseorderitem",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("finished_good__isnull", True), ("raw_material__isnull", False))
                    | models.Q(("finished_good__isnull", False), ("raw_material__isnull", True))
                ),
                name="purchase_item_has_exactly_one_stock_item",
            ),
        ),
    ]
