from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0003_production_batches_customer_links"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="transaction_type",
            field=models.CharField(
                choices=[("paid", "Paid"), ("unpaid", "Unpaid")],
                default="paid",
                help_text="Legacy field retained for historical physical-store orders; direct sales are recorded in Sales.",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="customer_payment_method",
            field=models.CharField(
                blank=True,
                default="Transfer",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="unpaid_description",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[("Cash", "Cash"), ("Card", "Card"), ("Transfer", "Transfer")],
                default="Cash",
                help_text="Legacy field retained for historical rows; customer-order payment is handled through Finance.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="shortage_flag",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="shortage_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.CreateModel(
            name="ProductionBatchReconciliation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reason", models.CharField(max_length=255)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="production_productionbatchreconciliation_set",
                    to="core.business",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="production_productionbatchreconciliation_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("source_batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="reconciliation_out",
                    to="production.productionbatch",
                )),
                ("target_batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="reconciliation_in",
                    to="production.productionbatch",
                )),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
