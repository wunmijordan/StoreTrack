import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_initial"),
        ("inventory", "0013_stockmovement_affects_stock"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Expense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField()),
                ("category", models.CharField(choices=[("utilities", "Utilities"), ("rent", "Rent / Premises"), ("maintenance", "Maintenance / Repairs"), ("transport", "Transport / Delivery"), ("labour", "Labour / Wages"), ("marketing", "Marketing"), ("bank", "Bank / Payment Fees"), ("other", "Other")], default="other", max_length=20)),
                ("description", models.CharField(max_length=180)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("vendor", models.CharField(blank=True, max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="expenses_created", to=settings.AUTH_USER_MODEL)),
                ("raw_material", models.ForeignKey(blank=True, help_text="Optional: link the expense to a specific inventory item when it is not a purchase order.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="misc_expenses", to="inventory.rawmaterial")),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
    ]
