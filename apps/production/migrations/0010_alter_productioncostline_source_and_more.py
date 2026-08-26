from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0009_historical_production_costing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productioncostline',
            name='source',
            field=models.CharField(default='latest_procurement', max_length=20),
        ),
        migrations.AlterField(
            model_name='productioncostsnapshot',
            name='business',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='core.business',
            ),
        ),
        migrations.AlterField(
            model_name='productioncostsnapshot',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                help_text='Who made this entry. Null for records created before this field existed.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='%(app_label)s_%(class)s_created',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='productioncostsnapshot',
            name='cost_source',
            field=models.CharField(default='latest_procurement', max_length=20),
        ),
    ]
