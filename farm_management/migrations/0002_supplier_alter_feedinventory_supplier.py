from django.db import migrations, models
import django.db.models.deletion


def migrate_supplier_data(apps, schema_editor):
    FeedInventory = apps.get_model('farm_management', 'FeedInventory')
    Supplier = apps.get_model('farm_management', 'Supplier')

    supplier_names = FeedInventory.objects.values_list('supplier', flat=True).distinct()
    supplier_names = [name for name in supplier_names if name]

    name_to_supplier = {}
    for name in supplier_names:
        supplier, created = Supplier.objects.get_or_create(name=name)
        name_to_supplier[name] = supplier

    for item in FeedInventory.objects.all():
        old_name = item.supplier
        if old_name and old_name in name_to_supplier:
            item.supplier = name_to_supplier[old_name]
            item.save(update_fields=['supplier'])


class Migration(migrations.Migration):

    dependencies = [
        ('farm_management', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='name')),
                ('phone', models.CharField(blank=True, max_length=20, verbose_name='phone')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email')),
                ('address', models.TextField(blank=True, verbose_name='address')),
                ('notes', models.TextField(blank=True, verbose_name='notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
            ],
            options={
                'verbose_name': 'supplier',
                'verbose_name_plural': 'suppliers',
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(
            migrate_supplier_data,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='feedinventory',
            name='supplier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='feed_inventory', to='farm_management.supplier', verbose_name='supplier'),
        ),
    ]