from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0010_storefront_hero_image_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="commercesettings",
            name="storefront_hero_image_scale",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("1.00"),
                help_text="Resize the rendered image from 50% to 200% while keeping its blend and focal point.",
                max_digits=3,
                validators=[
                    MinValueValidator(Decimal("0.50")),
                    MaxValueValidator(Decimal("2.00")),
                ],
            ),
        ),
    ]
