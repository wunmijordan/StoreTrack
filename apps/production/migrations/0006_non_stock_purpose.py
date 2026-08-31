from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("production", "0005_production_destination")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="non_stock_purpose",
            field=models.CharField(blank=True, default="", max_length=255, help_text="Specific purpose when production is not going to Physical Store stock (e.g. Staff Welfare, Gift, Charity)."),
        ),
    ]
