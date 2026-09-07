from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="commercesettings",
            name="connector_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
