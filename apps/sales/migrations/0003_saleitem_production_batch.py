from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_customer_master"),
        ("production", "0003_production_batches_customer_links"),
    ]
    operations = [
        migrations.AddField(
            model_name="saleitem",
            name="production_batch",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sale_items", to="production.productionbatch"),
        ),
    ]
