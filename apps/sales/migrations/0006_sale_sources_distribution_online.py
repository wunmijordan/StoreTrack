from django.db import migrations, models


def customer_sale_to_distribution(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    Sale.objects.filter(source="customer_order").update(source="distribution_order")


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0005_alter_sale_source"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sale",
            name="source",
            field=models.CharField(
                choices=[
                    ("walkin", "Physical Store"),
                    ("distribution_order", "Distribution Order"),
                    ("online_order", "Online Order"),
                ],
                default="walkin",
                max_length=20,
            ),
        ),
        migrations.RunPython(customer_sale_to_distribution, migrations.RunPython.noop),
    ]
