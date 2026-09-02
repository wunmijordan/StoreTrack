from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_business_order_numbers(apps, schema_editor):
    Order = apps.get_model("production", "Order")
    Sequence = apps.get_model("production", "OrderNumberSequence")
    by_business_max = {}
    for order in Order.objects.all().order_by("business_id", "id"):
        order.order_number = order.id
        order.save(update_fields=["order_number"])
        by_business_max[order.business_id] = max(by_business_max.get(order.business_id, 0), order.id)
    for business_id, max_number in by_business_max.items():
        Sequence.objects.update_or_create(
            business_id=business_id,
            defaults={"next_number": max_number + 1},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0013_alter_productionrun_business_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderNumberSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("next_number", models.PositiveBigIntegerField(default=1)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_ordernumbersequence_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_ordernumbersequence_created", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name="order",
            name="order_number",
            field=models.PositiveBigIntegerField(editable=False, null=True),
        ),
        migrations.RunPython(seed_business_order_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="order_number",
            field=models.PositiveBigIntegerField(editable=False),
        ),
        migrations.AddConstraint(
            model_name="ordernumbersequence",
            constraint=models.UniqueConstraint(fields=("business",), name="unique_order_number_sequence_per_business"),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(fields=("business", "order_number"), name="unique_order_number_per_business"),
        ),
    ]
