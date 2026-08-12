from django.db import migrations
from datetime import datetime


NIGERIAN_NAMES = {
    "admin": "Adebayo Ogunlesi",
    "farm manager": "Chioma Eze",
    "farm manager 2": "Chinedu Okafor",
    "customer": "Emeka Nwosu",
    "test": "Fatima Bello",
    "super admin": "Oluwaseun Adeyemi",
    "debug admin": "Ngozi Okonkwo",
    "debug admin 2": "Chidi Nwachukwu",
    "debug admin 3": "Amina Bello",
    "staff": "Yusuf Ibrahim",
    "test new user": "Zainab Hassan",
    "test admin": "Grace Oluwadare",
    "test manager": "Tunde Bakare",
    "admin test": "Kemi Adeyemi",
    "david 123": "David Okonkwo",
    "test pass": "Ifeanyi Obi",
    "superadmin": "Bolanle Adeyinka",
    "typography audit": "Seyi Alade",
    "davidgggg": "Gbenga Olaseun",
    "hub visual check": "Ayo Balogun",
    "test customer crud": "Nneka Eze",
    "testcustomercrud": "Nneka Eze",
}


def get_nigerian_name(full_name, role):
    name = full_name.strip().lower()
    if name in NIGERIAN_NAMES:
        return NIGERIAN_NAMES[name]
    if role == "SUPER_ADMIN":
        return "Adebayo Ogunlesi"
    if role == "FARM_MANAGER":
        return "Chioma Eze"
    if role == "STAFF":
        return "Yusuf Ibrahim"
    return "Emeka Nwosu"


def generate_username(first_name, last_name, year):
    base = f"{first_name}{last_name}{year}"
    return base


def update_usernames(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    users = CustomUser.objects.all().order_by("date_joined")

    year_counters = {}
    for user in users:
        year = user.date_joined.year
        year_counters[year] = year_counters.get(year, 0) + 1

        new_full_name = get_nigerian_name(user.full_name, user.role)
        user.full_name = new_full_name

        name_parts = new_full_name.split()
        first_name = name_parts[0] if name_parts else "User"
        last_name = "".join(name_parts[1:]) if len(name_parts) > 1 else ""

        base = f"{first_name}{last_name}{year}"
        seq = year_counters[year]
        user.username = f"{base}{seq:03d}"

        user.save(update_fields=["full_name", "username"])


def reverse_usernames(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    users = CustomUser.objects.all().order_by("date_joined")
    for i, user in enumerate(users, start=1):
        user.username = f"user{i}"
        user.save(update_fields=["username"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_customuser_default_delivery_address"),
    ]

    operations = [
        migrations.RunPython(update_usernames, reverse_usernames),
    ]
