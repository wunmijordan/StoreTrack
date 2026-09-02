from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("production", "0010_orderitem_production_plan"), ("sales", "0005_alter_customer_business_alter_customer_created_by_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AlterField(model_name="order", name="status", field=models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("completed", "Completed"), ("rejected", "Rejected"), ("reversed", "Reversed")], default="pending", max_length=10)),
        migrations.AddField(model_name="order", name="reversed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="order", name="reversed_reason", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="order", name="reversed_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reversed_production_orders", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="productionbatch", name="is_reversed", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="productionbatch", name="planned_surplus_customer_channel", field=models.CharField(blank=True, default="", max_length=20)),
        migrations.AddField(model_name="productionbatch", name="planned_surplus_customer_units", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AddField(model_name="productionbatch", name="planned_surplus_customer", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="planned_offcut_batches", to="sales.customer")),
        migrations.AddField(model_name="productionbatch", name="planned_surplus_sale", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="planned_offcut_batches", to="sales.sale")),
    ]
