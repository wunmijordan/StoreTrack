import commerce.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0008_commerce_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="commercesettings",
            name="storefront_headline",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional main storefront message. Leave blank to use wording tailored to your business type.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="commercesettings",
            name="storefront_hero_image",
            field=models.ImageField(
                blank=True,
                help_text="Optional wide image displayed in the storefront header.",
                upload_to=commerce.models.storefront_hero_image_upload_to,
            ),
        ),
    ]
