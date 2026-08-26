from decimal import Decimal
from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


def latest_cost(RawMaterialCostSnapshot, material_id, date, fallback):
    row = RawMaterialCostSnapshot.objects.filter(raw_material_id=material_id, effective_date__lte=date).order_by('-effective_date', '-id').first()
    return (row.usage_unit_cost, 'latest_procurement') if row else (fallback, 'legacy_current_cost')


def backfill_production_costs(apps, schema_editor):
    Order = apps.get_model('production', 'Order')
    Snapshot = apps.get_model('production', 'ProductionCostSnapshot')
    Line = apps.get_model('production', 'ProductionCostLine')
    RawMaterialCostSnapshot = apps.get_model('procurement', 'RawMaterialCostSnapshot')
    RecipeItem = apps.get_model('inventory', 'RecipeItem')
    ProductionMaterial = apps.get_model('inventory', 'ProductionMaterial')
    for order in Order.objects.filter(status='completed').prefetch_related('items'):
        date = order.completed_date or order.date
        for item in order.items.all():
            if Snapshot.objects.filter(order_item_id=item.pk).exists():
                continue
            good = item.finished_good
            upb = good.units_per_batch or Decimal('1')
            multiplier = item.batch_qty + (item.piece_qty / upb)
            snapshot = Snapshot.objects.create(
                business_id=order.business_id, order_id=order.pk, order_item_id=item.pk,
                finished_good_id=good.pk, production_date=date, produced_units=(item.batch_qty * upb + item.piece_qty),
            )
            total = Decimal('0'); sources = set()
            links = list(RecipeItem.objects.filter(finished_good_id=good.pk)) + list(ProductionMaterial.objects.filter(finished_good_id=good.pk))
            for link in links:
                material = link.raw_material
                cost, source = latest_cost(RawMaterialCostSnapshot, material.pk, date, material.cost_per_unit)
                qty = link.qty_per_batch * multiplier
                line_total = qty * cost
                total += line_total; sources.add(source)
                Line.objects.create(snapshot_id=snapshot.pk, raw_material_id=material.pk, quantity=qty, usage_unit_cost=cost, total_cost=line_total, source=source)
            snapshot.total_cost = total
            produced_units = (item.batch_qty * upb + item.piece_qty)
            snapshot.unit_cost = total / produced_units if produced_units else Decimal('0')
            snapshot.cost_source = 'latest_procurement' if sources == {'latest_procurement'} else 'latest_procurement_with_legacy_fallback'
            snapshot.save(update_fields=['total_cost', 'unit_cost', 'cost_source'])


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial'), ('inventory', '0016_historical_costing_and_channel_prices'), ('procurement', '0003_rawmaterialcostsnapshot'), ('production', '0008_alter_order_customer_name_alter_order_payment_method'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='ProductionCostSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('production_date', models.DateField()), ('produced_units', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('total_cost', models.DecimalField(decimal_places=4, default=0, max_digits=16)), ('unit_cost', models.DecimalField(decimal_places=6, default=0, max_digits=16)),
                ('cost_source', models.CharField(default='latest_procurement', max_length=20)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_set', to='core.business')),
                ('created_by', models.ForeignKey(blank=True, help_text='Who made this entry. Null for records created before this field existed.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('finished_good', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='production_cost_snapshots', to='inventory.finishedgood')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cost_snapshots', to='production.order')),
                ('order_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cost_snapshots', to='production.orderitem')),
            ], options={'ordering': ['-production_date', '-id']},
        ),
        migrations.CreateModel(
            name='ProductionCostLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.DecimalField(decimal_places=4, default=0, max_digits=14)), ('usage_unit_cost', models.DecimalField(decimal_places=6, default=0, max_digits=16)),
                ('total_cost', models.DecimalField(decimal_places=4, default=0, max_digits=16)), ('source', models.CharField(default='latest_procurement', max_length=20)),
                ('raw_material', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inventory.rawmaterial')),
                ('snapshot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='production.productioncostsnapshot')),
            ],
        ),
        migrations.RunPython(backfill_production_costs, migrations.RunPython.noop),
    ]
