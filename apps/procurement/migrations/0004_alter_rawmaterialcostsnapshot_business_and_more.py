from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('procurement', '0003_rawmaterialcostsnapshot'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rawmaterialcostsnapshot',
            name='business',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(app_label)s_%(class)s_set',
                to='core.business',
            ),
        ),
        migrations.AlterField(
            model_name='rawmaterialcostsnapshot',
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
    ]
