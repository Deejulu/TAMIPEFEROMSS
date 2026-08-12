import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farm_management', '0002_supplier_alter_feedinventory_supplier'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedlog',
            name='feed_inventory',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='feed_logs', to='farm_management.feedinventory', verbose_name='feed inventory'),
        ),
    ]