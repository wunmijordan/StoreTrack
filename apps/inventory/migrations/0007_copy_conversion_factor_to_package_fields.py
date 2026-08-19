from django.db import migrations


def copy_forward(apps, schema_editor):
    """Old model: purchase_unit -> usage_unit (was really the PACKAGE content
    unit, e.g. 'kg') -> conversion_factor (qty of that content per purchase
    unit, e.g. 50).

    New model separates the package layer from the fine dispensing layer:
    purchase_unit -> package_qty + package_unit -> usage_unit + usage_conversion_factor.

    Safe default for every existing row: package_qty/package_unit take the
    OLD conversion_factor/usage_unit values exactly (so 'package content'
    matches what was previously tracked), usage_conversion_factor is set to
    1 (no further breakdown yet). The usage_unit field itself keeps its
    stored value untouched — it already holds the right starting point.

    Net effect: total_conversion_factor (package_qty x usage_conversion_factor)
    equals the old conversion_factor exactly, so nothing about existing
    stock/cost numbers changes. Go into each material afterwards (Inventory
    page) and set its TRUE usage_unit + usage_conversion_factor where the
    recipe actually dispenses in something finer (e.g. sugar: usage_unit
    'g', usage_conversion_factor 1000)."""
    RawMaterial = apps.get_model("inventory", "RawMaterial")
    for m in RawMaterial.objects.all():
        m.package_qty = m.conversion_factor
        m.package_unit = m.usage_unit
        m.usage_conversion_factor = 1
        m.save(update_fields=["package_qty", "package_unit", "usage_conversion_factor"])


def copy_backward(apps, schema_editor):
    RawMaterial = apps.get_model("inventory", "RawMaterial")
    for m in RawMaterial.objects.all():
        m.conversion_factor = m.package_qty * m.usage_conversion_factor
        m.usage_unit = m.package_unit or m.usage_unit
        m.save(update_fields=["conversion_factor", "usage_unit"])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_add_package_and_usage_conversion_fields'),
    ]

    operations = [
        migrations.RunPython(copy_forward, copy_backward),
    ]
