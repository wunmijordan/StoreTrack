from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_business_background_color"),
    ]

    operations = [
        migrations.AlterField(
            model_name="business",
            name="vertical",
            field=models.CharField(
                choices=[
                    ("bakery", "Bakery"),
                    ("restaurant", "Restaurant / food service"),
                    ("general", "General production"),
                    ("wholesale", "Wholesale / distribution"),
                    ("retail", "Retail store"),
                ],
                default="bakery",
                max_length=20,
            ),
        ),
    ]
