from django.db import migrations, models
import django.db.models.deletion
from django.utils.translation import gettext_lazy as _


def flag_feed_inventory_without_category(apps, schema_editor):
    FeedInventory = apps.get_model('farm_management', 'FeedInventory')
    unmatched = FeedInventory.objects.filter(category__isnull=True)
    if unmatched.exists():
        names = [item.feed_type for item in unmatched]
        print(
            f"\n[FeedInventory migration] {unmatched.count()} existing feed inventory item(s) "
            f"have no category assigned. Review and assign a category manually in the admin: "
            f"{names}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('farm_management', '0008_category_convert_species_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedinventory',
            name='category',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='feed_inventory',
                to='farm_management.category',
                verbose_name=_('category'),
            ),
        ),
        migrations.RunPython(flag_feed_inventory_without_category, migrations.RunPython.noop),
    ]
