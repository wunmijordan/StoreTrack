from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipeitem",
            name="flexible_usage",
            field=models.BooleanField(
                default=False,
                help_text="Allow the quantity per batch to be adjusted when the production order is approved (useful for yeast or other urgency-sensitive ingredients).",
            ),
        ),
    ]
