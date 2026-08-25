from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("production", "0006_order_types_distribution_online")]
    operations = [
        migrations.AddField(
            model_name="order",
            name="customer_region",
            field=models.CharField(blank=True, help_text="Optional reporting region/territory for distribution or online customer analytics.", max_length=100),
        ),
        migrations.AddField(
            model_name="order",
            name="customer_group",
            field=models.CharField(blank=True, help_text="Optional customer group/segment for distribution or online customer analytics.", max_length=100),
        ),
    ]
