import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farm_management', '0004_populate_feedlog_feed_inventory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='feedlog',
            name='feed_inventory',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, related_name='feed_logs', to='farm_management.feedinventory', verbose_name='feed inventory'),
        ),
        migrations.RemoveField(
            model_name='feedlog',
            name='feed_type',
        ),
    ]