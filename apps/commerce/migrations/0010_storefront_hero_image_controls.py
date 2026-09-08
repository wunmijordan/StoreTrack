from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0009_storefront_personalization"),
    ]

    operations = [
        migrations.AddField(
            model_name="commercesettings",
            name="storefront_hero_image_fit",
            field=models.CharField(
                choices=[("cover", "Fill the header"), ("contain", "Show the full image")],
                default="cover",
                help_text="Fill the header for a crop, or show the full image without zooming in.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="commercesettings",
            name="storefront_hero_image_position",
            field=models.CharField(
                choices=[
                    ("left top", "Top left"),
                    ("center top", "Top centre"),
                    ("right top", "Top right"),
                    ("left center", "Centre left"),
                    ("center center", "Centre"),
                    ("right center", "Centre right"),
                    ("left bottom", "Bottom left"),
                    ("center bottom", "Bottom centre"),
                    ("right bottom", "Bottom right"),
                ],
                default="center center",
                help_text="Choose the part of the image that should stay in view.",
                max_length=20,
            ),
        ),
    ]
