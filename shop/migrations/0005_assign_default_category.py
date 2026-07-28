from django.db import migrations


def assign_default_category(apps, schema_editor):
    Category = apps.get_model("shop", "Category")
    Product = apps.get_model("shop", "Product")

    uncategorized, created = Category.objects.get_or_create(
        name="Uncategorized",
        defaults={"slug": "uncategorized", "description": "Products without a specific category"},
    )
    Product.objects.filter(category__isnull=True).update(category=uncategorized)


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0004_category_product_is_sample_data_product_category"),
    ]

    operations = [
        migrations.RunPython(assign_default_category, migrations.RunPython.noop),
    ]
