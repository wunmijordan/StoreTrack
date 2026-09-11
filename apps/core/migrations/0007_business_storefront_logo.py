# Generated for storefront tenant branding.
from django.core.validators import FileExtensionValidator
from django.db import migrations, models
import core.models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_update_default_brand_palette"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="storefront_logo",
            field=models.ImageField(
                blank=True,
                help_text="Optional logo shown beside the business name on the public storefront only.",
                upload_to=core.models.business_storefront_logo_upload_to,
                validators=[FileExtensionValidator(["jpeg", "jpg", "png", "webp"])],
            ),
        ),
    ]
