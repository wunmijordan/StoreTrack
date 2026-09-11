# Generated for INPROFIC Web Push support.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def mark_existing_notifications_processed(apps, schema_editor):
    CommerceNotification = apps.get_model("commerce", "CommerceNotification")
    CommerceNotification.objects.filter(push_processed_at__isnull=True).update(
        push_processed_at=django.utils.timezone.now()
    )


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0012_update_notification_brand_copy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="commercenotification",
            name="push_processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_notifications_processed, migrations.RunPython.noop),
        migrations.CreateModel(
            name="CommercePushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("endpoint", models.TextField()),
                ("endpoint_hash", models.CharField(max_length=64)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("user_agent", models.CharField(blank=True, default="", max_length=300)),
                ("active", models.BooleanField(default=True)),
                ("failure_count", models.PositiveSmallIntegerField(default=0)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_failure_at", models.DateTimeField(blank=True, null=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commerce_push_subscriptions", to="core.business")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commerce_push_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="commercepushsubscription",
            constraint=models.UniqueConstraint(fields=("business", "user", "endpoint_hash"), name="unique_commerce_push_device"),
        ),
        migrations.AddIndex(
            model_name="commercepushsubscription",
            index=models.Index(fields=["business", "active"], name="commerce_push_active_idx"),
        ),
        migrations.CreateModel(
            name="CommercePushDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("expired", "Subscription expired")], default="pending", max_length=12)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_deliveries", to="commerce.commercenotification")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="commerce.commercepushsubscription")),
            ],
            options={"ordering": ["next_attempt_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="commercepushdelivery",
            constraint=models.UniqueConstraint(fields=("notification", "subscription"), name="unique_commerce_push_delivery"),
        ),
        migrations.AddIndex(
            model_name="commercepushdelivery",
            index=models.Index(fields=["status", "next_attempt_at"], name="commerce_push_pending_idx"),
        ),
    ]
