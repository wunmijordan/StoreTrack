from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="customer_payment_status",
            field=models.CharField(
                choices=[("paid", "Received"), ("unpaid", "Receivable")],
                default="paid",
                help_text="Distribution/Online only: whether the customer payment has been received or remains a receivable.",
                max_length=10,
            ),
        ),
    ]
