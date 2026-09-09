import django.core.validators
from django.db import migrations, models


LEGACY_BACKGROUND = "#4D1C25"
LEGACY_ACCENT = "#8F172D"
NEW_BACKGROUND = "#050733"
NEW_ACCENT = "#D14900"


def update_legacy_palette(apps, schema_editor):
    Business = apps.get_model("core", "Business")
    Business.objects.filter(background_color__iexact=LEGACY_BACKGROUND).update(
        background_color=NEW_BACKGROUND
    )
    Business.objects.filter(accent_color__iexact=LEGACY_ACCENT).update(
        accent_color=NEW_ACCENT
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0005_add_wholesale_retail_verticals")]

    operations = [
        migrations.AlterField(
            model_name="business",
            name="accent_color",
            field=models.CharField(
                default=NEW_ACCENT,
                help_text="Used for primary buttons, links, headings, and action highlights.",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        "^#[0-9A-Fa-f]{6}$",
                        "Use a six-digit hex colour such as #D14900.",
                    )
                ],
            ),
        ),
        migrations.AlterField(
            model_name="business",
            name="background_color",
            field=models.CharField(
                default=NEW_BACKGROUND,
                help_text="Used for persistent branded backgrounds such as the navigation area.",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        "^#[0-9A-Fa-f]{6}$",
                        "Use a six-digit hex colour such as #050733.",
                    )
                ],
            ),
        ),
        # A reverse update could overwrite a tenant that independently chose the
        # new palette before this migration, so rollback deliberately keeps data.
        migrations.RunPython(update_legacy_palette, migrations.RunPython.noop),
    ]
