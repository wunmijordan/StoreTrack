from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_subscription_plans_and_commerce_module")]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="yearly_discount_percent",
            field=models.DecimalField(decimal_places=2, default=0, help_text="Discount applied to 12 months of the plan when paid yearly.", max_digits=5),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="billing_cycle",
            field=models.CharField(choices=[("monthly", "Monthly"), ("yearly", "Yearly")], default="monthly", max_length=12),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="provider",
            field=models.CharField(choices=[("paystack", "Paystack"), ("monnify", "Monnify"), ("manual", "Manual / founder confirmation")], default="manual", max_length=12),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="provider_reference",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="checkout_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="provider_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="subscriptionpayment",
            name="status",
            field=models.CharField(choices=[("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="pending", max_length=12),
        ),
    ]
