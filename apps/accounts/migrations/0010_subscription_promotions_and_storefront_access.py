from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_subscriptionpaymentsettings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="userbusiness",
            name="commerce_storefront_access",
            field=models.BooleanField(
                default=False,
                help_text="Allow this staff member to use the in-premise Commerce Storefront / POS without granting general Commerce administration access.",
            ),
        ),
        migrations.CreateModel(
            name="SubscriptionPromotion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(max_length=140)),
                ("discount_type", models.CharField(choices=[("percent", "Percentage off"), ("amount", "Fixed amount off")], max_length=12)),
                ("discount_value", models.DecimalField(decimal_places=2, max_digits=14)),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="subscription_promotions_created", to=settings.AUTH_USER_MODEL)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="promotions", to="accounts.subscriptionplan")),
            ],
            options={
                "ordering": ["-starts_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="subscriptionpromotion",
            index=models.Index(fields=["plan", "active", "starts_at", "ends_at"], name="plan_promo_active_idx"),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="base_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="promotion",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments", to="accounts.subscriptionpromotion"),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="promotion_discount_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="promotion_reason",
            field=models.CharField(blank=True, default="", max_length=140),
        ),
    ]
