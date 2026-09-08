import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0007_checkout_payment_boundary"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="commercesettings",
            name="notification_desktop_enabled",
            field=models.BooleanField(default=True, help_text="Use browser desktop alerts when this device has granted permission."),
        ),
        migrations.AddField(
            model_name="commercesettings",
            name="notification_sound_enabled",
            field=models.BooleanField(default=True, help_text="Play a short sound when new activity arrives while StoreTrack is open."),
        ),
        migrations.AddField(
            model_name="commercesettings",
            name="notifications_enabled",
            field=models.BooleanField(default=True, help_text="Show persistent in-app alerts for new commerce activity."),
        ),
        migrations.AddField(
            model_name="commercesettings",
            name="notify_order_activity",
            field=models.BooleanField(default=True, help_text="Alert when a website, API, or connector sends a checkout or order."),
        ),
        migrations.AddField(
            model_name="commercesettings",
            name="notify_payment_activity",
            field=models.BooleanField(default=True, help_text="Alert for payment attempts, transfer claims, confirmations, and payment reviews."),
        ),
        migrations.CreateModel(
            name="CommerceNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("event_type", models.CharField(choices=[("checkout_received", "Checkout received"), ("intake_received", "Order received"), ("payment_started", "Payment started"), ("payment_claim", "Payment claim submitted"), ("payment_confirmed", "Payment confirmed"), ("payment_review", "Payment needs review")], max_length=28)),
                ("title", models.CharField(max_length=160)),
                ("message", models.CharField(blank=True, default="", max_length=500)),
                ("target_url", models.CharField(blank=True, default="/commerce/", max_length=500)),
                ("dedupe_key", models.CharField(blank=True, default="", max_length=180)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="core.business")),
                ("created_by", models.ForeignKey(blank=True, help_text="Who made this entry. Null for records created before this field existed.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(app_label)s_%(class)s_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="CommerceNotificationRead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("read_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reads", to="commerce.commercenotification")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commerce_notification_reads", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="commercenotification",
            index=models.Index(fields=["business", "created_at"], name="commerce_notice_recent_idx"),
        ),
        migrations.AddConstraint(
            model_name="commercenotification",
            constraint=models.UniqueConstraint(condition=models.Q(("dedupe_key", ""), _negated=True), fields=("business", "dedupe_key"), name="unique_commerce_notification_dedupe"),
        ),
        migrations.AddConstraint(
            model_name="commercenotificationread",
            constraint=models.UniqueConstraint(fields=("notification", "user"), name="unique_commerce_notification_read"),
        ),
    ]
