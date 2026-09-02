import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_business_accent_color_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="business",
            name="accent_color",
            field=models.CharField(
                default="#8F172D",
                help_text="Used for primary buttons, links, headings, and action highlights.",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        "^#[0-9A-Fa-f]{6}$",
                        "Use a six-digit hex colour such as #8F172D.",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="business",
            name="background_color",
            field=models.CharField(
                default="#4D1C25",
                help_text="Used for persistent branded backgrounds such as the navigation area.",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        "^#[0-9A-Fa-f]{6}$",
                        "Use a six-digit hex colour such as #4D1C25.",
                    )
                ],
            ),
        ),
    ]
