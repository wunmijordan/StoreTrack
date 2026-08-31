from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_customers(apps, schema_editor):
    Customer = apps.get_model("sales", "Customer")
    Sale = apps.get_model("sales", "Sale")
    for sale in Sale.objects.exclude(customer="").exclude(customer="Walk-in"):
        name = (sale.customer or "").strip()
        if not name:
            continue
        customer, _ = Customer.objects.get_or_create(
            business_id=sale.business_id,
            name=name,
            defaults={"created_by_id": sale.created_by_id, "active": True},
        )
        if sale.customer_master_id is None:
            sale.customer_master_id = customer.pk
            sale.save(update_fields=["customer_master"])


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0001_initial"),
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("phone", models.CharField(blank=True, default="", max_length=40)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("address", models.TextField(blank=True, default="")),
                ("region", models.CharField(blank=True, default="", max_length=100)),
                ("customer_group", models.CharField(blank=True, default="", max_length=100)),
                ("credit_limit", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("payment_terms_days", models.PositiveIntegerField(default=0, help_text="Expected payment period in days for credit sales.")),
                ("active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_customer_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_customer_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(fields=("business", "name"), name="unique_customer_per_business"),
        ),
        migrations.AddField(
            model_name="sale",
            name="customer_master",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_records", to="sales.customer"),
        ),
        migrations.AddField(
            model_name="customerpayment",
            name="customer_master",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments", to="sales.customer"),
        ),
        migrations.RunPython(seed_customers, migrations.RunPython.noop),
    ]
