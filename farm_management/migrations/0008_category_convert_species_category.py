from django.db import migrations, models
import django.db.models.deletion
from django.utils.translation import gettext_lazy as _


def migrate_category_data(apps, schema_editor):
    """
    Create Category records from existing species category values and link species to them.
    """
    Species = apps.get_model('farm_management', 'Species')
    Category = apps.get_model('farm_management', 'Category')

    # Define category mapping - convert lowercase codes to proper display names
    category_mapping = {
        'fish': 'Fish',
        'poultry': 'Poultry',
    }

    # Get distinct category values from existing species
    existing_categories = Species.objects.values_list('category_old', flat=True).distinct()
    
    # Create Category records for all categories that exist in the database
    category_objects = {}
    for category_code in existing_categories:
        if category_code and category_code in category_mapping:
            display_name = category_mapping[category_code]
            category_obj, created = Category.objects.get_or_create(
                name=display_name,
                defaults={'is_active': True}
            )
            category_objects[category_code] = category_obj

    # Link all existing species to their corresponding Category record
    for species in Species.objects.all():
        old_category = species.category_old
        if old_category and old_category in category_objects:
            species.category = category_objects[old_category]
            species.save(update_fields=['category'])


class Migration(migrations.Migration):

    dependencies = [
        ('farm_management', '0007_species_convert_batch_species'),
    ]

    operations = [
        # Step 1: Create the Category model
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name=_('name'))),
                ('is_active', models.BooleanField(default=True, verbose_name=_('is active'))),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))),
            ],
            options={
                'verbose_name': _('category'),
                'verbose_name_plural': _('categories'),
                'ordering': ['name'],
            },
        ),
        
        # Step 2: Rename old category field to category_old (temporary)
        migrations.RenameField(
            model_name='species',
            old_name='category',
            new_name='category_old',
        ),
        
        # Step 3: Add new category ForeignKey field (nullable temporarily)
        migrations.AddField(
            model_name='species',
            name='category',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='species',
                to='farm_management.category',
                verbose_name=_('category')
            ),
        ),
        
        # Step 4: Migrate existing data - create Categories and link Species
        migrations.RunPython(migrate_category_data, migrations.RunPython.noop),
        
        # Step 5: Make category field non-nullable now that all species have been migrated
        migrations.AlterField(
            model_name='species',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='species',
                to='farm_management.category',
                verbose_name=_('category')
            ),
        ),
        
        # Step 6: Remove the old category field
        migrations.RemoveField(
            model_name='species',
            name='category_old',
        ),
        
        # Step 7: Update Species model ordering to use category__name instead of category
        migrations.AlterModelOptions(
            name='species',
            options={
                'ordering': ['category__name', 'name'],
                'verbose_name': _('species'),
                'verbose_name_plural': _('species'),
            },
        ),
    ]
