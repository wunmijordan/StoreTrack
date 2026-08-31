from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0003_saleitem_production_batch"),
        ("inventory", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerProductPrice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.CharField(choices=[("distribution", "Distribution"), ("online", "Online")], max_length=20)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_customerproductprice_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_customerproductprice_created", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_prices", to="sales.customer")),
                ("finished_good", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="customer_prices", to="inventory.finishedgood")),
            ],
            options={
                "ordering": ["finished_good__name", "channel"],
                "constraints": [
                    models.UniqueConstraint(fields=("business", "customer", "finished_good", "channel"), name="unique_customer_product_price"),
                ],
            },
        ),
    ]
