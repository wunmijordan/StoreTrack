from django.db import migrations, models


def customer_to_distribution(apps, schema_editor):
    Order = apps.get_model("production", "Order")
    Order.objects.filter(order_type="customer").update(order_type="distribution")


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0005_alter_order_order_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="order_type",
            field=models.CharField(
                choices=[
                    ("distribution", "Distribution Order"),
                    ("online", "Online Order"),
                    ("physical_store", "Physical Store Order"),
                ],
                default="physical_store",
                max_length=15,
            ),
        ),
        migrations.RunPython(customer_to_distribution, migrations.RunPython.noop),
    ]
