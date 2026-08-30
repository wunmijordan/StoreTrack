from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_roles_and_memberships"),
    ]
    operations = [
        migrations.AddField(
            model_name="role",
            name="visible_to_admin",
            field=models.BooleanField(
                default=True,
                help_text="Uncheck to keep this role visible only to the global superuser — for demo/review roles that aren't part of this business's normal operations. Business Admins won't see it in Roles & Access, can't open it directly, and can't assign it to a user.",
            ),
        ),
    ]
