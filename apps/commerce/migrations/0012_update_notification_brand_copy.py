from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0011_storefront_hero_image_scale"),
    ]

    operations = [
        migrations.AlterField(
            model_name="commercesettings",
            name="notification_sound_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Play a short sound when new activity arrives while INPROFIC is open.",
            ),
        ),
    ]
