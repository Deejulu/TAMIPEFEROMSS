"""
Management command to populate the entire site with realistic sample data.

Creates site content, shop categories/products, and farm_management records —
all tagged so they can be cleanly removed by delete_sample.

Idempotent: if sample data already exists, the command exits early without
creating duplicates. Use delete_sample first to wipe and reseed.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from admin_dashboard.models import SiteContent
from farm_management.models import (
    Category as FarmCategory,
    Species,
    Supplier,
    FeedInventory,
    Batch,
    FeedLog,
    GrowthRecord,
    MortalityLog,
    VaccinationRecord,
    HealthMedicationLog,
    DailyActivityLog,
    HarvestRecord,
)
from shop.models import Category as ShopCategory, Product

User = get_user_model()


# ---------------------------------------------------------------------------
# Site content
# ---------------------------------------------------------------------------
SITE_CONTENT_SECTIONS = [
    {
        "section": "homepage_hero",
        "title": "Welcome to Tamipee Farms",
        "content": (
            "<p>Fresh, quality agricultural products delivered to your door.</p>"
            "<p>We specialise in premium fish, poultry, and cattle raised with sustainable "
            "farming practices across our farms in Nigeria.</p>"
        ),
    },
    {
        "section": "shop_banner",
        "title": "Fresh Produce Available Now",
        "content": (
            "<p>20% off all fresh fish and poultry this week. "
            "Free delivery on orders above ₦15,000 within Lagos.</p>"
        ),
    },
    {
        "section": "about",
        "title": "About Tamipee Farms",
        "content": (
            "<p>Tamipee Farms is a family-owned agricultural business based in Nigeria. "
            "We raise fish, poultry, and cattle using modern farming techniques while "
            "preserving traditional quality standards.</p>"
            "<p>Our farm spans multiple locations with dedicated ponds, poultry pens, "
            "and grazing fields. We supply fresh products directly to consumers, "
            "restaurants, and retailers.</p>"
        ),
    },
    {
        "section": "contact",
        "title": "Contact Us",
        "content": (
            "<p><strong>Phone:</strong> +234 803 123 4567</p>"
            "<p><strong>Email:</strong> info@tamipeefarms.com.ng</p>"
            "<p><strong>Address:</strong> Km 15, Lagos-Ibadan Expressway, "
            "Ogun State, Nigeria</p>"
        ),
    },
    {
        "section": "faq",
        "title": "Frequently Asked Questions",
        "content": (
            "<p><strong>How long does delivery take?</strong><br>"
            "Same-day delivery in Lagos, next-day delivery in Ogun and Oyo states.</p>"
            "<p><strong>Are your products fresh?</strong><br>"
            "Yes — all our products are harvested or processed on-site and "
            "delivered within 24 hours.</p>"
            "<p><strong>Do you offer bulk orders?</strong><br>"
            "Yes, contact us directly for wholesale pricing.</p>"
        ),
    },
    {
        "section": "delivery_info",
        "title": "Delivery Information",
        "content": (
            "<p>We deliver nationwide using trusted logistics partners.</p>"
            "<ul>"
            "<li><strong>Lagos:</strong> Same-day (₦1,500)</li>"
            "<li><strong>Ogun / Oyo:</strong> Next-day (₦2,500)</li>"
            "<li><strong>Other states:</strong> 2-3 business days (₦3,500)</li>"
            "</ul>"
        ),
    },
    {
        "section": "terms_privacy",
        "title": "Terms & Privacy Policy",
        "content": (
            "<p>By using our website, you agree to our terms of service. "
            "We respect your privacy and do not share personal data with third parties.</p>"
        ),
    },
    {
        "section": "return_refund",
        "title": "Return & Refund Policy",
        "content": (
            "<p>Fresh produce cannot be returned once delivered. "
            "If you receive damaged or incorrect items, please contact us within 24 hours "
            "for a replacement or refund.</p>"
        ),
    },
    {
        "section": "business_hours",
        "title": "Business Hours",
        "content": (
            "<p>Monday – Friday: 8:00 AM – 6:00 PM</p>"
            "<p>Saturday: 9:00 AM – 4:00 PM</p>"
            "<p>Sunday: Closed</p>"
        ),
    },
    {
        "section": "social_media",
        "title": "Connect With Us",
        "content": (
            "<p>Follow us for updates, farming tips, and special offers.</p>"
        ),
        "facebook_url": "https://www.facebook.com/tamipeefarms",
        "instagram_url": "https://www.instagram.com/tamipeefarms",
        "twitter_url": "https://x.com/tamipeefarms",
        "tiktok_url": "https://www.tiktok.com/@tamipeefarms",
        "whatsapp_url": "https://wa.me/2348031234567",
    },
]

# ---------------------------------------------------------------------------
# Shop data
# ---------------------------------------------------------------------------
SHOP_CATEGORIES = [
    {"name": "Fresh Fish & Seafood", "description": "Live and processed fish from our ponds"},
    {"name": "Poultry & Eggs", "description": "Fresh poultry and eggs from our free-range pens"},
    {"name": "Livestock", "description": "Quality cattle and small ruminants"},
    {"name": "Fresh Produce", "description": "Seasonal vegetables and fruits"},
    {"name": "Animal Feed", "description": "Nutritionally balanced feeds for all species"},
    {"name": "Farm Supplies", "description": "Tools, fertilizers, and pesticides"},
]

SHOP_PRODUCTS = [
    {"name": "Live Catfish (per kg)", "category": "Fresh Fish & Seafood", "price": 2800, "stock_quantity": 200},
    {"name": "Live Tilapia (per kg)", "category": "Fresh Fish & Seafood", "price": 2400, "stock_quantity": 180},
    {"name": "Smoked Catfish (per kg)", "category": "Fresh Fish & Seafood", "price": 5200, "stock_quantity": 80},
    {"name": "Dry Catfish (per kg)", "category": "Fresh Fish & Seafood", "price": 4500, "stock_quantity": 60},
    {"name": "Live Broiler Chicken (per bird)", "category": "Poultry & Eggs", "price": 3800, "stock_quantity": 150},
    {"name": "Live Layer Chicken (per bird)", "category": "Poultry & Eggs", "price": 4500, "stock_quantity": 100},
    {"name": "Live Turkey (per bird)", "category": "Poultry & Eggs", "price": 9500, "stock_quantity": 40},
    {"name": "Fresh Eggs (30 pcs)", "category": "Poultry & Eggs", "price": 3200, "stock_quantity": 120},
    {"name": "Calf (per head)", "category": "Livestock", "price": 180000, "stock_quantity": 5},
    {"name": "Ram (per head)", "category": "Livestock", "price": 120000, "stock_quantity": 8},
    {"name": "Fresh Tomatoes (per kg)", "category": "Fresh Produce", "price": 1500, "stock_quantity": 300},
    {"name": "Fresh Pepper (per kg)", "category": "Fresh Produce", "price": 1200, "stock_quantity": 250},
    {"name": "Fresh Okra (per kg)", "category": "Fresh Produce", "price": 900, "stock_quantity": 200},
    {"name": "Onions (per kg)", "category": "Fresh Produce", "price": 800, "stock_quantity": 400},
    {"name": "Broiler Starter Feed (50kg)", "category": "Animal Feed", "price": 14500, "stock_quantity": 50},
    {"name": "Layer Grower Feed (50kg)", "category": "Animal Feed", "price": 13000, "stock_quantity": 45},
    {"name": "Cattle Feed (50kg)", "category": "Animal Feed", "price": 10500, "stock_quantity": 40},
    {"name": "Fish Feed 4mm (50kg)", "category": "Animal Feed", "price": 16000, "stock_quantity": 35},
    {"name": "NPK Fertilizer (50kg)", "category": "Farm Supplies", "price": 28000, "stock_quantity": 25},
    {"name": "Organic Pesticide (1L)", "category": "Farm Supplies", "price": 4200, "stock_quantity": 60},
    {"name": "Hand Hoe", "category": "Farm Supplies", "price": 3500, "stock_quantity": 30},
    {"name": "Wheelbarrow", "category": "Farm Supplies", "price": 35000, "stock_quantity": 10},
]

# ---------------------------------------------------------------------------
# Farm management data (same as before)
# ---------------------------------------------------------------------------
SAMPLE_CATEGORIES = [
    {"name": "Fish", "species": ["Catfish", "Tilapia"]},
    {"name": "Poultry", "species": ["Broiler", "Layer", "Turkey"]},
    {"name": "Cattle", "species": ["White Fulani", "Sokoto Gudali"]},
]

SAMPLE_SUPPLIERS = [
    {
        "name": "AgriFeed Nigeria Ltd",
        "phone": "0803-123-4567",
        "email": "info@agrifeed.ng",
        "address": "Plot 12, Lekki-Epe Expressway, Victoria Island, Lagos, Nigeria",
    },
    {
        "name": "PoultryMax Supplies",
        "phone": "0809-876-5432",
        "email": "sales@poultrymax.ng",
        "address": "45 Iyaganku Road, Ibadan, Oyo State, Nigeria",
    },
    {
        "name": "AquaTech Fisheries",
        "phone": "0807-555-1212",
        "email": "contact@aquatechfish.ng",
        "address": "78 Port Harcourt-Owerri Road, Port Harcourt, Rivers State, Nigeria",
    },
    {
        "name": "Savanna Livestock Co",
        "phone": "0805-444-3333",
        "email": "info@savanna-livestock.ng",
        "address": "Kano Municipal, Kano State, Nigeria",
    },
    {
        "name": "VetMed Pharmaceuticals",
        "phone": "0802-777-8888",
        "email": "support@vetmedpharma.ng",
        "address": "Plot 5 Wuse District, Abuja, FCT, Nigeria",
    },
]

SAMPLE_FEED_INVENTORY = [
    {
        "feed_type": "Coppens 4mm Fish Feed",
        "category_name": "Fish",
        "supplier_name": "AquaTech Fisheries",
        "quantity_on_hand_kg": 500,
        "cost_per_kg": Decimal("500.00"),
        "reorder_point_kg": 100,
    },
    {
        "feed_type": "Efurudibe Catfish Crumbs",
        "category_name": "Fish",
        "supplier_name": "AquaTech Fisheries",
        "quantity_on_hand_kg": 300,
        "cost_per_kg": Decimal("450.00"),
        "reorder_point_kg": 75,
    },
    {
        "feed_type": "Vital Feed Grower Mash",
        "category_name": "Poultry",
        "supplier_name": "PoultryMax Supplies",
        "quantity_on_hand_kg": 800,
        "cost_per_kg": Decimal("400.00"),
        "reorder_point_kg": 200,
    },
    {
        "feed_type": "Top Chick Starter Cracks",
        "category_name": "Poultry",
        "supplier_name": "PoultryMax Supplies",
        "quantity_on_hand_kg": 400,
        "cost_per_kg": Decimal("450.00"),
        "reorder_point_kg": 100,
    },
    {
        "feed_type": "Mazi International Cattle Feed",
        "category_name": "Cattle",
        "supplier_name": "Savanna Livestock Co",
        "quantity_on_hand_kg": 600,
        "cost_per_kg": Decimal("350.00"),
        "reorder_point_kg": 150,
    },
]

SAMPLE_BATCHES = [
    {"name": "Broiler Batch - July 2026", "species": "Broiler", "initial_count": 500, "days_ago": 30, "season": "rainy"},
    {"name": "Layer Batch - June 2026", "species": "Layer", "initial_count": 300, "days_ago": 45, "season": "rainy"},
    {"name": "Catfish Batch - July 2026", "species": "Catfish", "initial_count": 1000, "days_ago": 30, "season": "rainy"},
    {"name": "Tilapia Batch - June 2026", "species": "Tilapia", "initial_count": 800, "days_ago": 45, "season": "rainy"},
    {"name": "White Fulani Cattle - Aug 2025", "species": "White Fulani", "initial_count": 25, "days_ago": 180, "season": "dry"},
    {"name": "Sokoto Gudali - Mar 2026", "species": "Sokoto Gudali", "initial_count": 30, "days_ago": 140, "season": "dry"},
]


def _growth_weights_for(category_name, species_name, initial_count):
    """Return a list of increasing average weights (kg) for the given species."""
    if species_name == "Broiler":
        return [Decimal("0.050"), Decimal("1.000"), Decimal("2.100")]
    if species_name == "Layer":
        return [Decimal("0.050"), Decimal("1.200"), Decimal("1.800")]
    if species_name == "Turkey":
        return [Decimal("0.055"), Decimal("3.500"), Decimal("6.200")]
    if species_name == "Catfish":
        return [Decimal("0.005"), Decimal("0.150"), Decimal("0.400")]
    if species_name == "Tilapia":
        return [Decimal("0.005"), Decimal("0.100"), Decimal("0.300")]
    if species_name == "White Fulani":
        return [Decimal("50.000"), Decimal("150.000"), Decimal("250.000")]
    if species_name == "Sokoto Gudali":
        return [Decimal("60.000"), Decimal("180.000"), Decimal("300.000")]
    return [Decimal("1.000"), Decimal("2.000"), Decimal("3.000")]


class Command(BaseCommand):
    help = "Populate the entire site with realistic sample data (is_sample=True / is_sample_data=True)."

    def handle(self, *args, **options):
        today = date.today()

        # ------------------------------------------------------------------
        # Idempotency: skip if any sample data already exists
        # ------------------------------------------------------------------
        from django.db.models import Q
        sample_exists = (
            SiteContent.objects.filter(is_sample=True).exists() or
            Batch.objects.filter(is_sample=True).exists() or
            Product.objects.filter(is_sample_data=True).exists()
        )
        if sample_exists:
            self.stdout.write(
                self.style.WARNING(
                    "Sample data already exists. Run 'delete_sample' first to wipe and reseed."
                )
            )
            return

        # ------------------------------------------------------------------
        # 1. Site content sections — update with realistic demo content
        # ------------------------------------------------------------------
        for section_data in SITE_CONTENT_SECTIONS:
            section_code = section_data.pop("section")
            section_data.setdefault("is_sample", True)
            obj, _ = SiteContent.objects.update_or_create(
                section=section_code,
                defaults=section_data,
            )
            self.stdout.write(f"Updated site content: {section_code}")

        # ------------------------------------------------------------------
        # 2. Shop categories and products
        # ------------------------------------------------------------------
        category_map = {}
        for cat_data in SHOP_CATEGORIES:
            cat, created = ShopCategory.objects.get_or_create(
                name=cat_data["name"],
                defaults={"description": cat_data["description"], "is_sample_data": True},
            )
            category_map[cat_data["name"]] = cat
            if created:
                self.stdout.write(f"Created shop category: {cat.name}")

        products_created = 0
        for prod_data in SHOP_PRODUCTS:
            cat = category_map[prod_data["category"]]
            product, created = Product.objects.get_or_create(
                name=prod_data["name"],
                defaults={
                    "category": cat,
                    "price": prod_data["price"],
                    "stock_quantity": prod_data["stock_quantity"],
                    "is_sample_data": True,
                },
            )
            if created:
                products_created += 1
        if products_created:
            self.stdout.write(f"Created {products_created} shop products.")

        # ------------------------------------------------------------------
        # 3. Farm management data
        # ------------------------------------------------------------------
        farm_category_map = {}
        for cat_data in SAMPLE_CATEGORIES:
            cat, created = FarmCategory.objects.get_or_create(
                name=cat_data["name"],
                defaults={"is_active": True, "is_sample": True},
            )
            if created:
                self.stdout.write(f"Created farm category: {cat.name}")
            farm_category_map[cat.name] = cat

        species_map = {}
        for cat_data in SAMPLE_CATEGORIES:
            cat = farm_category_map[cat_data["name"]]
            for spp_name in cat_data["species"]:
                spp, created = Species.objects.get_or_create(
                    name=spp_name,
                    defaults={"category": cat, "is_active": True, "is_sample": True},
                )
                if created:
                    self.stdout.write(f"Created species: {spp.name} ({cat.name})")
                species_map[spp_name] = spp

        supplier_map = {}
        for sup_data in SAMPLE_SUPPLIERS:
            sup, created = Supplier.objects.get_or_create(
                name=sup_data["name"],
                defaults={
                    "phone": sup_data["phone"],
                    "email": sup_data["email"],
                    "address": sup_data["address"],
                    "is_sample": True,
                },
            )
            if created:
                self.stdout.write(f"Created supplier: {sup.name}")
            supplier_map[sup.name] = sup

        feed_inv_map = {}
        for fi_data in SAMPLE_FEED_INVENTORY:
            cat = farm_category_map[fi_data["category_name"]]
            sup = supplier_map[fi_data["supplier_name"]]
            fi, created = FeedInventory.objects.get_or_create(
                feed_type=fi_data["feed_type"],
                defaults={
                    "category": cat,
                    "supplier": sup,
                    "quantity_on_hand_kg": fi_data["quantity_on_hand_kg"],
                    "cost_per_kg": fi_data["cost_per_kg"],
                    "reorder_point_kg": fi_data["reorder_point_kg"],
                    "is_sample": True,
                },
            )
            if created:
                self.stdout.write(f"Created feed inventory: {fi.feed_type}")
            feed_inv_map[fi_data["feed_type"]] = fi

        feed_by_category = {}
        for fi in FeedInventory.objects.filter(is_sample=True):
            if fi.category:
                feed_by_category.setdefault(fi.category.name, []).append(fi)

        for b_data in SAMPLE_BATCHES:
            spp = species_map[b_data["species"]]
            start = today - timedelta(days=b_data["days_ago"])
            batch = Batch.objects.create(
                name=b_data["name"],
                species=spp,
                initial_count=b_data["initial_count"],
                start_date=start,
                season=b_data["season"],
                is_sample=True,
            )
            self.stdout.write(f"Created batch: {batch.name} ({spp.name})")

            cat_name = spp.category.name
            cat_feeds = feed_by_category.get(cat_name, [])

            for i in range(3):
                log_date = start + timedelta(days=i * 7)
                feed_inv = cat_feeds[i % len(cat_feeds)] if cat_feeds else None
                qty = Decimal("50.0") if feed_inv else Decimal("0.00")
                FeedLog.objects.create(
                    batch=batch, date=log_date, feed_inventory=feed_inv,
                    quantity_kg=qty, is_sample=True,
                )

            growth_weights = _growth_weights_for(cat_name, b_data["species"], batch.initial_count)
            for i in range(min(len(growth_weights), 3)):
                gdate = start + timedelta(days=i * 14)
                sample_n = max(1, batch.initial_count // 10)
                GrowthRecord.objects.create(
                    batch=batch, date=gdate, average_weight_kg=growth_weights[i],
                    sample_size=sample_n, is_sample=True,
                )

            mort_count = max(1, batch.initial_count // 50)
            mortality_dates = [start + timedelta(days=10)]
            if b_data["initial_count"] >= 200:
                mortality_dates.append(start + timedelta(days=25))
            for mdate in mortality_dates:
                MortalityLog.objects.create(
                    batch=batch, date=mdate, count=mort_count,
                    cause="Natural mortality" if cat_name == "Cattle" else "Disease outbreak",
                    notes="Adjusted feed and medication response.",
                    is_sample=True,
                )

            if not batch.is_fish:
                vaccine_dates = [start, start + timedelta(days=21)]
                vaccine_name = "NDV + IB Vaccine" if cat_name == "Poultry" else "Blackleg Vaccine"
                for vdate in vaccine_dates:
                    if vdate <= today:
                        VaccinationRecord.objects.create(
                            batch=batch, date=vdate, vaccine_name=vaccine_name,
                            dosage="0.5ml per bird" if cat_name == "Poultry" else "1ml per head",
                            administered_by="Dr. Okafor", is_sample=True,
                        )

            health_scenarios = [
                {"medicine": "Oxytetracycline", "dosage": "20mg/kg", "reason": "Respiratory infection treatment", "admin": "Dr. Okafor", "days_after": 5},
                {"medicine": "Albendazole", "dosage": "10mg/kg", "reason": "Deworming routine", "admin": "Farm Manager", "days_after": 15},
            ]
            if cat_name == "Poultry":
                health_scenarios.append({"medicine": "Amprolium", "dosage": "2g/L water", "reason": "Coccidiosis prevention", "admin": "Dr. Okafor", "days_after": 10})
            elif cat_name == "Cattle":
                health_scenarios.append({"medicine": "Penicillin", "dosage": "6ml per head", "reason": "Wound infection", "admin": "Vet Nurse", "days_after": 8})
            for h_scenario in health_scenarios:
                hdate = start + timedelta(days=h_scenario["days_after"])
                if hdate <= today:
                    HealthMedicationLog.objects.create(
                        batch=batch, date=hdate, medicine_name=h_scenario["medicine"],
                        dosage=h_scenario["dosage"], reason=h_scenario["reason"],
                        administered_by=h_scenario["admin"], is_sample=True,
                    )

            activity_notes = [
                "Checked feeding troughs and replenished feed. All animals healthy.",
                "Cleaned pens and replaced bedding. Monitored water levels.",
                "Observed normal behavior and activity levels. No signs of distress.",
            ]
            if cat_name == "Poultry":
                activity_notes.append("Collected eggs and checked nesting boxes. Mortality count recorded.")
            elif cat_name == "Fish":
                activity_notes.append("Checked water quality parameters (pH, temperature, oxygen). Normal readings.")
            for idx, note in enumerate(activity_notes[:3]):
                adate = start + timedelta(days=idx * 7 + 2)
                if adate <= today:
                    DailyActivityLog.objects.create(
                        batch=batch, date=adate, note=note,
                        created_by=None, is_sample=True,
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "Sample data populated successfully across site content, shop, and farm management."
            )
        )
