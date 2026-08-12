from django.db import migrations


def regenerate_usernames_for_fixed_names(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    users = CustomUser.objects.all().order_by("date_joined")

    year_counters = {}
    for user in users:
        year = user.date_joined.year
        year_counters[year] = year_counters.get(year, 0) + 1

        name_parts = user.full_name.split()
        first_name = name_parts[0] if name_parts else "User"
        last_name = "".join(name_parts[1:]) if len(name_parts) > 1 else ""

        base = f"{first_name}{last_name}{year}"
        seq = year_counters[year]
        new_username = f"{base}{seq:03d}"

        if user.username != new_username:
            user.username = new_username
            user.save(update_fields=["username"])


def reverse_regenerate(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_fix_remaining_usernames"),
    ]

    operations = [
        migrations.RunPython(regenerate_usernames_for_fixed_names, reverse_regenerate),
    ]
