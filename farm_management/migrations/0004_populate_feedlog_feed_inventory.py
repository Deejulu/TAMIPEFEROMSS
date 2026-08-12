from django.db import migrations


def populate_feed_inventory(apps, schema_editor):
    FeedLog = apps.get_model('farm_management', 'FeedLog')
    FeedInventory = apps.get_model('farm_management', 'FeedInventory')

    unmatched = []
    for log in FeedLog.objects.all():
        if log.feed_type:
            try:
                inventory = FeedInventory.objects.get(feed_type=log.feed_type)
                log.feed_inventory = inventory
                log.save(update_fields=['feed_inventory'])
            except FeedInventory.DoesNotExist:
                unmatched.append(log.feed_type)
            except FeedInventory.MultipleObjectsReturned:
                inventory = FeedInventory.objects.filter(feed_type=log.feed_type).first()
                log.feed_inventory = inventory
                log.save(update_fields=['feed_inventory'])

    if unmatched:
        unique_unmatched = sorted(set(unmatched))
        print(
            f"\n[FeedLog migration] {len(unique_unmatched)} unmatched feed_type value(s) "
            f"could not be mapped to a FeedInventory record. "
            f"Review and create matching FeedInventory items manually: {unique_unmatched}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('farm_management', '0003_add_feedlog_feed_inventory'),
    ]

    operations = [
        migrations.RunPython(populate_feed_inventory, migrations.RunPython.noop),
    ]