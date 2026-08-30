from django.db import migrations


def hide_superuser_role(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(key="superuser", visible_to_admin=True).update(visible_to_admin=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_role_visible_to_admin"),
    ]
    operations = [
        migrations.RunPython(hide_superuser_role, noop),
    ]
