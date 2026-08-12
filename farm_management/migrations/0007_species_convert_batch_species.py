from django.db import migrations, models
import django.db.models.deletion


def migrate_species_data(apps, schema_editor):
    """
    Create Species records from existing batch species values and link batches to them.
    """
    Batch = apps.get_model('farm_management', 'Batch')
    Species = apps.get_model('farm_management', 'Species')

    # Define species mapping with their categories
    species_mapping = {
        'catfish': ('Catfish', 'fish'),
        'tilapia': ('Tilapia', 'fish'),
        'broiler': ('Broiler (Poultry)', 'poultry'),
        'layer': ('Layer (Poultry)', 'poultry'),
    }

    # Get distinct species values from existing batches
    existing_species = Batch.objects.values_list('species_old', flat=True).distinct()
    
    # Create Species records for all species that exist in the database
    species_objects = {}
    for species_code in existing_species:
        if species_code and species_code in species_mapping:
            name, category = species_mapping[species_code]
            species_obj, created = Species.objects.get_or_create(
                name=name,
                defaults={'category': category, 'is_active': True}
            )
            species_objects[species_code] = species_obj

    # Link all existing batches to their corresponding Species record
    for batch in Batch.objects.all():
        old_species = batch.species_old
        if old_species and old_species in species_objects:
            batch.species = species_objects[old_species]
            batch.save(update_fields=['species'])


class Migration(migrations.Migration):

    dependencies = [
        ('farm_management', '0006_alter_feedlog_feed_inventory'),
    ]

    operations = [
        # Step 1: Create the Species model
        migrations.CreateModel(
            name='Species',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='name')),
                ('category', models.CharField(choices=[('fish', 'Fish'), ('poultry', 'Poultry')], max_length=20, verbose_name='category')),
                ('is_active', models.BooleanField(default=True, verbose_name='is active')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
            ],
            options={
                'verbose_name': 'species',
                'verbose_name_plural': 'species',
                'ordering': ['category', 'name'],
            },
        ),
        
        # Step 2: Rename the old species field to species_old (temporary)
        migrations.RenameField(
            model_name='batch',
            old_name='species',
            new_name='species_old',
        ),
        
        # Step 3: Add the new species ForeignKey field (nullable temporarily for migration)
        migrations.AddField(
            model_name='batch',
            name='species',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='batches',
                to='farm_management.species',
                verbose_name='species'
            ),
        ),
        
        # Step 4: Migrate data from species_old to species
        migrations.RunPython(
            migrate_species_data,
            migrations.RunPython.noop,
        ),
        
        # Step 5: Make the species field non-nullable
        migrations.AlterField(
            model_name='batch',
            name='species',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='batches',
                to='farm_management.species',
                verbose_name='species'
            ),
        ),
        
        # Step 6: Remove the old species_old field
        migrations.RemoveField(
            model_name='batch',
            name='species_old',
        ),
    ]
