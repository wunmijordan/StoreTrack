from django.db import migrations, models


def backfill_sale_costs(apps, schema_editor):
    SaleItem = apps.get_model('sales', 'SaleItem')
    ProductionCostSnapshot = apps.get_model('production', 'ProductionCostSnapshot')
    for item in SaleItem.objects.select_related('sale', 'finished_good').filter(unit_cost__isnull=True):
        snapshot = None
        if item.sale.linked_order_id:
            snapshot = ProductionCostSnapshot.objects.filter(order_id=item.sale.linked_order_id, finished_good_id=item.finished_good_id).order_by('-id').first()
        if not snapshot:
            snapshot = ProductionCostSnapshot.objects.filter(finished_good_id=item.finished_good_id, production_date__lte=item.sale.date).order_by('-production_date', '-id').first()
        if snapshot:
            item.unit_cost = snapshot.unit_cost
            item.save(update_fields=['unit_cost'])


class Migration(migrations.Migration):
    dependencies = [('production', '0009_historical_production_costing'), ('sales', '0007_alter_sale_linked_order')]
    operations = [
        migrations.AddField(model_name='saleitem', name='unit_cost', field=models.DecimalField(blank=True, decimal_places=6, help_text='Historical finished-good cost per unit at the time of sale.', max_digits=16, null=True)),
        migrations.RunPython(backfill_sale_costs, migrations.RunPython.noop),
    ]
