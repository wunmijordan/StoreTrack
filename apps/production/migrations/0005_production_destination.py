from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0004_shortage_reconciliation"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="production_destination",
            field=models.CharField(
                choices=[
                    ("store", "Store replenishment — add to Physical Store stock"),
                    ("non_stock", "Non-stock purpose — do not add to Physical Store stock"),
                ],
                default="store",
                help_text="Physical Store orders only: choose whether completed production enters Shelf Stock or is for a non-stock purpose.",
                max_length=12,
            ),
        ),
    ]
