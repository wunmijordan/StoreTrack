from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("expenses", "0001_initial")]
    operations = [migrations.RemoveField(model_name="expense", name="raw_material")]
