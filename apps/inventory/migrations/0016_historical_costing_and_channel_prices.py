from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('inventory', '0015_alter_rawmaterial_category')]
    operations = [
        migrations.AlterField(
            model_name='rawmaterial', name='cost_per_unit',
            field=models.DecimalField(default=0, max_digits=16, decimal_places=6),
        ),
        migrations.AlterField(
            model_name='finishedgood', name='stock',
            field=models.DecimalField(blank=True, default=None, help_text='Physical store (shelf) stock. Leave blank when this product is not stocked in the physical store.', max_digits=12, decimal_places=2, null=True),
        ),
        migrations.AlterField(
            model_name='finishedgood', name='reorder_level',
            field=models.DecimalField(blank=True, default=None, help_text='Physical-store reorder threshold in individual units. Leave blank when this product is not stocked in the physical store.', max_digits=12, decimal_places=2, null=True),
        ),
        migrations.CreateModel(
            name='FinishedGoodChannelPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('channel', models.CharField(choices=[('physical_store', 'Physical Store'), ('distribution', 'Distribution'), ('online', 'Online')], max_length=20)),
                ('price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('finished_good', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='channel_prices', to='inventory.finishedgood')),
            ],
            options={'ordering': ['channel'], 'unique_together': {('finished_good', 'channel')}},
        ),
    ]
