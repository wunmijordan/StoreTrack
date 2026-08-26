from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_cost_snapshots(apps, schema_editor):
    PurchaseOrderItem = apps.get_model('procurement', 'PurchaseOrderItem')
    Snapshot = apps.get_model('procurement', 'RawMaterialCostSnapshot')
    for item in PurchaseOrderItem.objects.select_related('purchase_order', 'raw_material').filter(purchase_order__status='received'):
        po = item.purchase_order
        material = item.raw_material
        factor = (material.package_qty or 1) * (material.usage_conversion_factor or 1)
        usage = item.unit_cost / factor if factor else item.unit_cost
        Snapshot.objects.get_or_create(
            purchase_order_item_id=item.pk,
            defaults={
                'business_id': po.business_id,
                'raw_material_id': material.pk,
                'effective_date': po.received_date or po.date,
                'purchase_unit_cost': item.unit_cost,
                'usage_unit_cost': usage,
                'supplier': po.supplier or '',
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
        ('inventory', '0016_historical_costing_and_channel_prices'),
        ('procurement', '0002_purchaseorder_created_by'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='RawMaterialCostSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('effective_date', models.DateField()),
                ('purchase_unit_cost', models.DecimalField(decimal_places=2, max_digits=12)),
                ('usage_unit_cost', models.DecimalField(decimal_places=6, max_digits=16)),
                ('supplier', models.CharField(blank=True, max_length=120)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='procurement_rawmaterialcostsnapshot_set', to='core.business')),
                ('created_by', models.ForeignKey(blank=True, help_text='Who made this entry. Null for records created before this field existed.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='procurement_rawmaterialcostsnapshot_created', to=settings.AUTH_USER_MODEL)),
                ('purchase_order_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cost_snapshots', to='procurement.purchaseorderitem')),
                ('raw_material', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cost_snapshots', to='inventory.rawmaterial')),
            ],
            options={'ordering': ['-effective_date', '-id']},
        ),
        migrations.RunPython(backfill_cost_snapshots, migrations.RunPython.noop),
    ]
