from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def seed_system_roles(apps, schema_editor):
    Business = apps.get_model("core", "Business")
    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    system = [
        ("stock_keeper", "Stock Keeper"), ("manager", "Manager"),
        ("accountant", "Accountant"), ("md_director", "MD / Director"),
        ("business_admin", "Business Admin"), ("superuser", "Superuser"),
    ]
    defaults = {
        "stock_keeper": {"dashboard":(1,0),"inventory":(1,1),"procurement":(1,1),"production":(1,1),"sales":(1,0),"expenses":(0,0),"finance":(0,0),"reports":(1,0),"users":(0,0)},
        "manager": {m:(1,1) for m in ["dashboard","inventory","procurement","production","sales","expenses","finance","reports"]} | {"users":(0,0)},
        "accountant": {"dashboard":(1,0),"inventory":(1,0),"procurement":(1,0),"production":(1,0),"sales":(1,0),"expenses":(1,1),"finance":(1,1),"reports":(1,1),"users":(0,0)},
        "md_director": {"dashboard":(1,0),"inventory":(1,0),"procurement":(1,0),"production":(1,0),"sales":(1,0),"expenses":(1,0),"finance":(1,1),"reports":(1,1),"users":(1,0)},
        "business_admin": {m:(1,1) for m in ["dashboard","inventory","procurement","production","sales","expenses","finance","reports","users"]},
        "superuser": {m:(1,1) for m in ["dashboard","inventory","procurement","production","sales","expenses","finance","reports","users"]},
    }
    for business in Business.objects.all():
        for key,name in system:
            role,_=Role.objects.get_or_create(business_id=business.pk,key=key,defaults={"name":name,"is_system":True,"active":True})
            for module,(view,edit) in defaults[key].items():
                RoleModulePermission.objects.get_or_create(role_id=role.pk,module=module,defaults={"can_view":bool(view),"can_edit":bool(edit)})


class Migration(migrations.Migration):
    dependencies = [("accounts","0001_initial"),("core","0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=60)), ("name", models.CharField(max_length=80)),
                ("is_system", models.BooleanField(default=False)), ("active", models.BooleanField(default=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="roles", to="core.business")),
            ],
            options={"ordering":["name"],"constraints":[models.UniqueConstraint(fields=("business","key"),name="unique_role_key_per_business"),models.UniqueConstraint(fields=("business","name"),name="unique_role_name_per_business")]},
        ),
        migrations.CreateModel(
            name="RoleModulePermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module", models.CharField(choices=[("dashboard","Dashboard"),("inventory","Inventory"),("procurement","Procurement"),("production","Production Orders"),("sales","Sales"),("expenses","Expenses"),("finance","Finance"),("reports","Reports"),("users","User Management")], max_length=30)),
                ("can_view", models.BooleanField(default=False)), ("can_edit", models.BooleanField(default=False)),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="module_permissions", to="accounts.role")),
            ],
            options={"ordering":["module"],"constraints":[models.UniqueConstraint(fields=("role","module"),name="unique_role_module_permission")]},
        ),
        migrations.CreateModel(
            name="UserBusiness",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("active", models.BooleanField(default=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_memberships", to="core.business")),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="memberships", to="accounts.role")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="business_memberships", to=settings.AUTH_USER_MODEL)),
            ], options={"constraints":[models.UniqueConstraint(fields=("user","business"),name="unique_user_business_membership")]},
        ),
        migrations.CreateModel(
            name="UserModulePermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module", models.CharField(choices=[("dashboard","Dashboard"),("inventory","Inventory"),("procurement","Procurement"),("production","Production Orders"),("sales","Sales"),("expenses","Expenses"),("finance","Finance"),("reports","Reports"),("users","User Management")], max_length=30)),
                ("can_view", models.BooleanField(blank=True, default=None, null=True)), ("can_edit", models.BooleanField(blank=True, default=None, null=True)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="module_permissions", to="accounts.userbusiness")),
            ], options={"ordering":["module"],"constraints":[models.UniqueConstraint(fields=("membership","module"),name="unique_user_module_permission")]},
        ),
        migrations.RunPython(seed_system_roles, migrations.RunPython.noop),
    ]
