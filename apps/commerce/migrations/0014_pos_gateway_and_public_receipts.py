import uuid

from django.db import migrations, models
import django.db.models.deletion


def populate_receipt_public_ids(apps, schema_editor):
    """Assign a distinct UUID to every pre-existing receipt before uniqueness is enforced.

    Adding a non-null unique field with a callable default in a single schema step is
    unsafe on populated SQLite tables because the table-remake path can evaluate the
    default once and reuse it for every copied row. Populate explicitly first, then
    make the field non-null/unique in the following AlterField operation.
    """
    Receipt = apps.get_model("commerce", "CommercePaymentReceipt")
    database_alias = schema_editor.connection.alias
    queryset = Receipt.objects.using(database_alias).filter(public_id__isnull=True).only("pk")

    batch = []
    seen = set()
    for receipt in queryset.iterator(chunk_size=500):
        candidate = uuid.uuid4()
        while candidate in seen:
            candidate = uuid.uuid4()
        seen.add(candidate)
        receipt.public_id = candidate
        batch.append(receipt)
        if len(batch) >= 500:
            Receipt.objects.using(database_alias).bulk_update(batch, ["public_id"], batch_size=500)
            batch.clear()

    if batch:
        Receipt.objects.using(database_alias).bulk_update(batch, ["public_id"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0013_web_push"),
        ("core", "0007_business_storefront_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="commercepaymentconfiguration",
            name="paystack_terminal_account",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="commerce_paystack_terminal_configurations", to="core.cashaccount"),
        ),
        migrations.AddField(
            model_name="commercepaymentconfiguration",
            name="paystack_terminal_customer_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="commercepaymentconfiguration",
            name="paystack_terminal_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="commercepaymentconfiguration",
            name="paystack_terminal_id",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="commercepaymentconfiguration",
            name="bank_transfer_provider",
            field=models.CharField(
                choices=[("paystack", "Paystack"), ("monnify", "Monnify")],
                default="paystack",
                help_text="Gateway that issues the temporary transfer account and confirms payment automatically.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="commercepaymentconfiguration",
            name="monnify_transfer_bank_code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Monnify bank code used to issue the temporary transfer account. Configure the bank your merchant account supports.",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="commercepayment",
            name="gateway_provider",
            field=models.CharField(blank=True, choices=[("", "No gateway"), ("paystack", "Paystack"), ("monnify", "Monnify")], default="", max_length=20),
        ),
        migrations.AddField(
            model_name="commercepaymentreceipt",
            name="public_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(
            populate_receipt_public_ids,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="commercepaymentreceipt",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="commercepayment",
            name="method",
            field=models.CharField(choices=[("paystack", "Paystack secure checkout"), ("monnify", "Monnify secure checkout"), ("bank_transfer", "Instant bank transfer"), ("cash", "Cash"), ("pos_card", "Card on POS terminal")], max_length=20),
        ),
        migrations.AlterField(
            model_name="commerceintake",
            name="source",
            field=models.CharField(choices=[("storefront", "Hosted storefront"), ("api", "API"), ("connector", "External connector"), ("staff_pos", "In-premise storefront")], default="storefront", max_length=12),
        ),
        migrations.AlterField(
            model_name="commercecheckoutsession",
            name="source",
            field=models.CharField(choices=[("storefront", "Hosted storefront"), ("api", "API"), ("connector", "External connector"), ("staff_pos", "In-premise storefront")], default="api", max_length=12),
        ),
    ]
