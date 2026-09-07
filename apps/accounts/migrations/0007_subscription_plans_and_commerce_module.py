# Additive SaaS entitlement layer. Existing businesses are not enrolled automatically.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


MODULES = (
    "dashboard", "inventory", "procurement", "production", "sales",
    "expenses", "finance", "reports", "users", "commerce",
)
PLAN_MATRIX = {
    "starter": {"dashboard":"full","inventory":"full","sales":"full","expenses":"full","reports":"basic","users":"full"},
    "production": {"dashboard":"full","inventory":"full","procurement":"full","production":"full","sales":"full","expenses":"full","reports":"full","users":"full"},
    "business_pro": {m:"full" for m in MODULES},
}


def seed_plans_and_commerce_permissions(apps, schema_editor):
    Business = apps.get_model("core", "Business")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RoleModulePermission")
    BusinessAccess = apps.get_model("accounts", "BusinessModuleAccess")
    Plan = apps.get_model("accounts", "SubscriptionPlan")
    PlanModule = apps.get_model("accounts", "SubscriptionPlanModule")
    names = {"starter":"STARTER", "production":"PRODUCTION", "business_pro":"BUSINESS PRO"}
    for code, name in names.items():
        plan, _ = Plan.objects.get_or_create(code=code, defaults={"name":name,"monthly_price":0,"trial_days":30,"additional_service_discount_percent":30})
        for module in MODULES:
            level = PLAN_MATRIX[code].get(module, "none")
            PlanModule.objects.update_or_create(plan=plan, module=module, defaults={"enabled":level != "none", "level":level})
    # Commerce is opt-in for all pre-existing businesses. This avoids making a
    # newly deployed public surface available simply because legacy missing rows mean enabled.
    for business_id in Business.objects.values_list("id", flat=True):
        BusinessAccess.objects.get_or_create(business_id=business_id, module="commerce", defaults={"enabled":False,"source":"legacy"})
    for role in Role.objects.all():
        RolePermission.objects.get_or_create(
            role_id=role.id, module="commerce",
            defaults={"can_view": role.key in {"business_admin", "superuser"}, "can_edit": role.key in {"business_admin", "superuser"}},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_businessmoduleaccess"),
        ("core", "0005_add_wholesale_retail_verticals"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(model_name="rolemodulepermission", name="module", field=models.CharField(choices=[("dashboard","Dashboard"),("inventory","Inventory"),("procurement","Procurement"),("production","Production Orders"),("sales","Sales"),("expenses","Expenses"),("finance","Finance"),("reports","Reports"),("users","User Management"),("commerce","Commerce")], max_length=30)),
        migrations.AlterField(model_name="usermodulepermission", name="module", field=models.CharField(choices=[("dashboard","Dashboard"),("inventory","Inventory"),("procurement","Procurement"),("production","Production Orders"),("sales","Sales"),("expenses","Expenses"),("finance","Finance"),("reports","Reports"),("users","User Management"),("commerce","Commerce")], max_length=30)),
        migrations.AlterField(model_name="businessmoduleaccess", name="module", field=models.CharField(choices=[("dashboard","Dashboard"),("inventory","Inventory"),("procurement","Procurement"),("production","Production Orders"),("sales","Sales"),("expenses","Expenses"),("finance","Finance"),("reports","Reports"),("users","User Management"),("commerce","Commerce")], max_length=30)),
        migrations.AlterField(model_name="businessmoduleaccess", name="source", field=models.CharField(choices=[("default","Service default"),("legacy","Legacy full access"),("plan","Subscription plan"),("founder","Founder lifetime grant")], default="default", max_length=12)),
        migrations.CreateModel(name="SubscriptionPlan", fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("code",models.CharField(choices=[("starter","STARTER"),("production","PRODUCTION"),("business_pro","BUSINESS PRO")],max_length=30,unique=True)),
            ("name",models.CharField(max_length=80)),("monthly_price",models.DecimalField(decimal_places=2,default=0,max_digits=14)),
            ("additional_service_discount_percent",models.DecimalField(decimal_places=2,default=30,help_text="Discount from the plan's normal monthly price for each additional service/business profile.",max_digits=5)),
            ("trial_days",models.PositiveSmallIntegerField(default=30)),("active",models.BooleanField(default=True)),
        ], options={"ordering":["monthly_price","id"]}),
        migrations.CreateModel(name="SubscriptionPlanModule", fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("module",models.CharField(choices=[("dashboard","Dashboard"),("inventory","Inventory"),("procurement","Procurement"),("production","Production Orders"),("sales","Sales"),("expenses","Expenses"),("finance","Finance"),("reports","Reports"),("users","User Management"),("commerce","Commerce")],max_length=30)),
            ("enabled",models.BooleanField(default=False)),("level",models.CharField(choices=[("none","Not included"),("basic","Basic"),("full","Full")],default="full",max_length=10)),
            ("plan",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="module_entitlements",to="accounts.subscriptionplan")),
        ], options={"ordering":["module"],"constraints":[models.UniqueConstraint(fields=("plan","module"),name="unique_plan_module")]}),
        migrations.CreateModel(name="BusinessSubscription", fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("status",models.CharField(choices=[("trial","Free trial"),("active","Paid"),("expired","Expired"),("founder","Founder lifetime")],default="trial",max_length=12)),
            ("started_at",models.DateTimeField(auto_now_add=True)),("trial_ends_at",models.DateTimeField(blank=True,null=True)),("paid_until",models.DateTimeField(blank=True,null=True)),
            ("founder_lifetime",models.BooleanField(default=False)),("founder_granted_at",models.DateTimeField(blank=True,null=True)),("founder_note",models.CharField(blank=True,default="",max_length=255)),
            ("founder_granted_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="founder_grants_made",to=settings.AUTH_USER_MODEL)),
            ("plan",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="subscriptions",to="accounts.subscriptionplan")),
            ("primary_business",models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name="subscription",to="core.business")),
        ], options={"ordering":["primary_business__name"]}),
        migrations.CreateModel(name="SubscriptionService", fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("is_primary",models.BooleanField(default=False)),("added_at",models.DateTimeField(auto_now_add=True)),
            ("business",models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name="subscription_service",to="core.business")),
            ("subscription",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="services",to="accounts.businesssubscription")),
        ], options={"ordering":["-is_primary","business__name"],"constraints":[models.UniqueConstraint(condition=models.Q(("is_primary",True)),fields=("subscription",),name="one_primary_service_per_subscription")]}),
        migrations.CreateModel(name="BusinessFeatureAccess", fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("feature",models.CharField(max_length=60)),("enabled",models.BooleanField(default=False)),
            ("source",models.CharField(choices=[("default","Service default"),("legacy","Legacy full access"),("plan","Subscription plan"),("founder","Founder lifetime grant")],default="plan",max_length=12)),
            ("business",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="feature_access",to="core.business")),
        ], options={"ordering":["feature"],"constraints":[models.UniqueConstraint(fields=("business","feature"),name="unique_business_feature_access")]}),
        migrations.CreateModel(name="SubscriptionPayment", fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("amount",models.DecimalField(decimal_places=2,max_digits=14)),("service_count",models.PositiveSmallIntegerField(default=1)),("months",models.PositiveSmallIntegerField(default=1)),
            ("status",models.CharField(choices=[("pending","Pending"),("paid","Paid"),("cancelled","Cancelled")],default="pending",max_length=12)),("reference",models.CharField(max_length=80,unique=True)),("created_at",models.DateTimeField(auto_now_add=True)),("paid_at",models.DateTimeField(blank=True,null=True)),("notes",models.CharField(blank=True,default="",max_length=255)),
            ("plan",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to="accounts.subscriptionplan")),("subscription",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="subscription_payments",to="accounts.businesssubscription")),
        ], options={"ordering":["-created_at","-id"]}),
        migrations.RunPython(seed_plans_and_commerce_permissions, migrations.RunPython.noop),
    ]
