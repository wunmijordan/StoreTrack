import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0004_rawmaterial_stock_3dp"),
        ("production", "0018_order_is_market_stock"),
        ("sales", "0006_sale_service_mode_sale_table_reference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="finishedgood",
            name="transferred_market_stock",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Remaining shelf stock that entered through an explicit Market Stock transfer. This is the only shelf-sale allowance for products not normally configured for Physical Store stock.",
                max_digits=14,
            ),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="movement_type",
            field=models.CharField(
                choices=[
                    ("raw_purchase", "Raw material purchase"),
                    ("raw_consumption", "Raw material consumption"),
                    ("fg_production", "Finished goods production"),
                    ("fg_sale", "Finished goods sale"),
                    ("fg_unpaid_issue", "Unpaid product issue"),
                    ("fg_wastage", "Production wastage"),
                    ("fg_market_production", "Production received into Distribution Market Stock"),
                    ("fg_market_release", "Market Stock released to distributor"),
                    ("fg_market_return", "Redistributable Distribution return"),
                    ("fg_market_transfer", "Market Stock transferred to Physical Store"),
                    ("fg_market_expiry", "Expired Market Stock write-off"),
                    ("fg_distribution_damage", "Damaged Distribution return"),
                    ("operational_dispense", "Operational supply dispense"),
                    ("adjustment", "Adjustment"),
                ],
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="MarketStockLot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source", models.CharField(choices=[("production", "Market-stock production"), ("return", "Redistributable customer return")], max_length=12)),
                ("received_date", models.DateField()),
                ("expiry_date", models.DateField(blank=True, null=True)),
                ("quantity_received", models.DecimalField(decimal_places=2, max_digits=14)),
                ("quantity_available", models.DecimalField(decimal_places=2, max_digits=14)),
                ("unit_cost", models.DecimalField(decimal_places=6, default=0, max_digits=16)),
                ("active", models.BooleanField(default=True)),
                ("closed_reason", models.CharField(blank=True, default="", max_length=40)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(app_label)s_%(class)s_created", to=settings.AUTH_USER_MODEL)),
                ("finished_good", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="market_stock_lots", to="inventory.finishedgood")),
                ("production_batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="market_stock_lots", to="production.productionbatch")),
                ("source_sale_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="returned_market_lots", to="sales.saleitem")),
            ],
            options={"ordering": ["expiry_date", "received_date", "id"]},
        ),
        migrations.CreateModel(
            name="MarketStockMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField()),
                ("movement_type", models.CharField(choices=[("production_in", "Production received into Market Stock"), ("release", "Released to distributor"), ("return_in", "Redistributable return received"), ("transfer_physical", "Transferred to Physical Store"), ("expiry", "Expired / unsellable write-off"), ("reversal", "Production reversal")], max_length=24)),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=14)),
                ("balance_after", models.DecimalField(decimal_places=2, max_digits=14)),
                ("unit_value", models.DecimalField(decimal_places=6, default=0, max_digits=16)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(app_label)s_%(class)s_created", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="market_stock_movements", to="sales.customer")),
                ("lot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movements", to="inventory.marketstocklot")),
                ("sale", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="market_stock_movements", to="sales.sale")),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.CreateModel(
            name="DistributionReturn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField()),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=14)),
                ("condition", models.CharField(choices=[("redistributable", "Unsold and suitable for redistribution"), ("damaged", "Damaged / unsellable")], max_length=20)),
                ("reason", models.CharField(max_length=255)),
                ("unit_value", models.DecimalField(decimal_places=6, default=0, max_digits=16)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(app_label)s_%(class)s_created", to=settings.AUTH_USER_MODEL)),
                ("market_lot", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="distribution_return", to="inventory.marketstocklot")),
                ("sale_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="distribution_returns", to="sales.saleitem")),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="marketstocklot",
            constraint=models.CheckConstraint(condition=models.Q(quantity_received__gte=0), name="market_lot_received_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="marketstocklot",
            constraint=models.CheckConstraint(condition=models.Q(quantity_available__gte=0), name="market_lot_available_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="marketstocklot",
            constraint=models.CheckConstraint(condition=models.Q(quantity_available__lte=models.F("quantity_received")), name="market_lot_available_not_above_received"),
        ),
        migrations.AddConstraint(
            model_name="marketstocklot",
            constraint=models.UniqueConstraint(condition=models.Q(source="production"), fields=("production_batch",), name="one_market_production_lot_per_batch"),
        ),
        migrations.AddConstraint(
            model_name="distributionreturn",
            constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0), name="distribution_return_quantity_positive"),
        ),
    ]
