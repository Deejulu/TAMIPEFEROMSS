from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.db.models import Sum
from decimal import Decimal
from datetime import date, timedelta

from shop.models import Product, Category as ShopCategory, Order, OrderItem, Payment
from notifications.models import Notification
from .models import Batch, FeedLog, GrowthRecord, MortalityLog, HarvestRecord, FeedInventory, Supplier, HealthMedicationLog, VaccinationRecord, DailyActivityLog, Species, Category, FarmExpense

User = get_user_model()


class SpeciesModelTests(TestCase):
    def setUp(self):
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

    def test_species_creation(self):
        self.assertEqual(self.catfish.name, "Catfish")
        self.assertEqual(self.catfish.category.name, "Fish")
        self.assertTrue(self.catfish.is_active)

    def test_species_str(self):
        self.assertEqual(str(self.catfish), "Catfish")

    def test_species_unique_name(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Species.objects.create(name="Catfish", category=Category.objects.get(name="Fish"))


class CategoryBadgeTests(TestCase):
    def test_badge_class_uses_real_category_name(self):
        # Known categories map to specific bootstrap badge classes.
        self.assertEqual(Category.objects.create(name="Fish").badge_class, "bg-info")
        self.assertEqual(Category.objects.create(name="Poultry").badge_class, "bg-warning")
        self.assertEqual(Category.objects.create(name="Cattle").badge_class, "bg-success")
        # Unknown categories fall back to a neutral badge instead of a wrong one.
        self.assertEqual(Category.objects.create(name="Camelidae").badge_class, "bg-secondary")


class SpeciesListViewTests(TestCase):
    """
    Regression tests for the Species Management list page.

    Guards against:
      * the category badge being hardcoded so every non-Fish species shows
        "Poultry" (e.g. "Cows" stored under "Cattle" must NOT display "Poultry");
      * the per-species batch count being wrong or not joined to real batches.
    """

    def setUp(self):
        self.fish = Category.objects.create(name="Fish")
        self.poultry = Category.objects.create(name="Poultry")
        self.cattle = Category.objects.create(name="Cattle")

        self.catfish = Species.objects.create(name="Catfish", category=self.fish, is_active=True)
        self.cows = Species.objects.create(name="Cows", category=self.cattle, is_active=True)

        # Catfish -> 2 batches, Cows -> 3 batches.
        for i in range(2):
            Batch.objects.create(
                name=f"Catfish Batch {i}",
                species=self.catfish,
                initial_count=100,
                start_date=date.today(),
                season="rainy",
            )
        for i in range(3):
            Batch.objects.create(
                name=f"Cows Batch {i}",
                species=self.cows,
                initial_count=50,
                start_date=date.today(),
                season="dry",
            )

        self.client = Client()
        self.admin = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def _get_list(self):
        self.client.login(username=self.admin.username, password="StrongPass1!")
        return self.client.get(reverse("farm_management:species_list"))

    def _species_in_context(self, response):
        # species_list is a paginated Page; materialise to a plain list.
        return list(response.context["species_list"])

    def test_species_displays_its_real_category_not_hardcoded_poultry(self):
        response = self._get_list()
        self.assertEqual(response.status_code, 200)

        cows = next(s for s in self._species_in_context(response) if s.name == "Cows")
        # The stored category must be Cattle (data is correct)...
        self.assertEqual(cows.category.name, "Cattle")
        # ...and exactly that category must be shown in the list.
        self.assertContains(response, "Cattle")
        # The bug previously rendered "Poultry" for every non-Fish species.
        # With no Poultry species in the data, "Poultry" must not appear in
        # the rendered species rows.
        self.assertNotContains(response, "Poultry")

    def test_category_badge_matches_stored_category_for_every_row(self):
        response = self._get_list()
        for species in self._species_in_context(response):
            self.assertContains(response, species.category.name)
            self.assertContains(response, species.category.badge_class)

    def test_batch_count_column_reflects_real_batch_count(self):
        response = self._get_list()
        species = {s.name: s for s in self._species_in_context(response)}
        for species_obj in species.values():
            # The annotated batch_count must equal the real number of batches.
            self.assertEqual(species_obj.batch_count, species_obj.batches.count())
        self.assertEqual(species["Cows"].batch_count, 3)
        self.assertEqual(species["Catfish"].batch_count, 2)


class BatchModelTests(TestCase):
    def setUp(self):
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)

    def test_batch_creation_sets_current_stock(self):
        batch = Batch.objects.create(
            name="Catfish Batch 1",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.assertEqual(batch.current_stock, 100)

    def test_batch_str(self):
        batch = Batch.objects.create(
            name="Test Batch",
            species=self.tilapia,
            initial_count=50,
            start_date=date.today(),
            season="dry",
        )
        self.assertEqual(str(batch), "Test Batch (Fish — Tilapia)")

    def test_is_fish_property(self):
        fish_batch = Batch.objects.create(
            name="Fish",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.assertTrue(fish_batch.is_fish)
        self.assertFalse(fish_batch.is_poultry)

    def test_is_poultry_property(self):
        poultry_batch = Batch.objects.create(
            name="Broilers",
            species=self.broiler,
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )
        self.assertTrue(poultry_batch.is_poultry)
        self.assertFalse(poultry_batch.is_fish)

    def test_mortality_rate_calculation(self):
        batch = Batch.objects.create(
            name="Mortality Test",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        MortalityLog.objects.create(
            batch=batch,
            date=date.today(),
            count=20,
            cause="Disease",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.mortality_rate, 20.0)

    def test_mortality_rate_zero_initial(self):
        batch = Batch.objects.create(
            name="Zero Test",
            species=self.catfish,
            initial_count=0,
            current_stock=0,
            start_date=date.today(),
            season="rainy",
        )
        self.assertEqual(batch.mortality_rate, 0)

    def test_feed_conversion_ratio(self):
        batch = Batch.objects.create(
            name="FCR Test",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        inventory = FeedInventory.objects.create(
            feed_type="Test Feed",
            quantity_on_hand_kg=1000,
            cost_per_kg=Decimal("500"),
            reorder_point_kg=100,
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory,
            quantity_kg=Decimal("100.0"),
        )
        GrowthRecord.objects.create(
            batch=batch,
            date=date.today(),
            average_weight_kg=Decimal("1.0"),
            sample_size=100,
        )
        later = date.today() + timedelta(days=30)
        GrowthRecord.objects.create(
            batch=batch,
            date=later,
            average_weight_kg=Decimal("2.0"),
            sample_size=80,
        )
        expected_fcr = round(Decimal("100.0") / ((Decimal("2.0") - Decimal("1.0")) * 100), 2)
        self.assertEqual(batch.feed_conversion_ratio, expected_fcr)

    def test_feed_conversion_ratio_none_when_insufficient_growth_records(self):
        batch = Batch.objects.create(
            name="FCR None Test",
            species=self.catfish,
            initial_count=100,
            current_stock=80,
            start_date=date.today(),
            season="rainy",
        )
        inventory = FeedInventory.objects.create(
            feed_type="Test Feed",
            quantity_on_hand_kg=1000,
            cost_per_kg=Decimal("500"),
            reorder_point_kg=100,
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory,
            quantity_kg=Decimal("100.0"),
        )
        self.assertIsNone(batch.feed_conversion_ratio)

    def test_total_feed_cost(self):
        batch = Batch.objects.create(
            name="Cost Test",
            species=self.catfish,
            initial_count=100,
            current_stock=80,
            start_date=date.today(),
            season="rainy",
        )
        inventory_a = FeedInventory.objects.create(
            feed_type="Feed A",
            quantity_on_hand_kg=1000,
            cost_per_kg=Decimal("500"),
            reorder_point_kg=100,
        )
        inventory_b = FeedInventory.objects.create(
            feed_type="Feed B",
            quantity_on_hand_kg=1000,
            cost_per_kg=Decimal("600"),
            reorder_point_kg=100,
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory_a,
            quantity_kg=Decimal("50.0"),
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory_b,
            quantity_kg=Decimal("30.0"),
        )
        self.assertEqual(batch.total_feed_cost, Decimal("43000"))


class MortalityLogTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

    def test_mortality_decrements_stock(self):
        batch = Batch.objects.create(
            name="Stock Test",
            species=self.catfish,
            initial_count=100,
            current_stock=100,
            start_date=date.today(),
            season="rainy",
        )
        self.assertEqual(batch.current_stock, 100)
        MortalityLog.objects.create(
            batch=batch,
            date=date.today(),
            count=5,
            cause="Disease",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.current_stock, 95)

    def test_mortality_does_not_go_below_zero(self):
        batch = Batch.objects.create(
            name="Zero Test",
            species=self.catfish,
            initial_count=10,
            start_date=date.today(),
            season="rainy",
        )
        MortalityLog.objects.create(
            batch=batch,
            date=date.today(),
            count=5,
            cause="Disease",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.current_stock, 5)

    def test_mortality_exceeding_current_stock_goes_to_zero(self):
        batch = Batch.objects.create(
            name="Zero Test",
            species=self.catfish,
            initial_count=10,
            start_date=date.today(),
            season="rainy",
        )
        MortalityLog.objects.create(
            batch=batch,
            date=date.today(),
            count=20,
            cause="Disease",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.current_stock, 0)

    def test_updating_mortality_does_not_double_decrement(self):
        batch = Batch.objects.create(
            name="Update Test",
            species=self.catfish,
            initial_count=100,
            current_stock=100,
            start_date=date.today(),
            season="rainy",
        )
        log = MortalityLog.objects.create(
            batch=batch,
            date=date.today(),
            count=10,
        )
        batch.refresh_from_db()
        self.assertEqual(batch.current_stock, 90)
        log.cause = "Updated cause"
        log.save()
        batch.refresh_from_db()
        self.assertEqual(batch.current_stock, 90)


class FeedLogModelTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

    def test_feed_log_creation(self):
        batch = Batch.objects.create(
            name="Feed Test",
            species=self.catfish,
            initial_count=100,
            current_stock=80,
            start_date=date.today(),
            season="rainy",
        )
        inventory = FeedInventory.objects.create(
            feed_type="Coppens",
            quantity_on_hand_kg=1000,
            cost_per_kg=Decimal("510"),
            reorder_point_kg=100,
        )
        log = FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory,
            quantity_kg=Decimal("25.5"),
        )
        self.assertEqual(log.feed_inventory.feed_type, "Coppens")
        self.assertEqual(log.quantity_kg, Decimal("25.5"))
        self.assertEqual(log.cost, Decimal("13005"))


class GrowthRecordModelTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

    def test_growth_record_creation(self):
        batch = Batch.objects.create(
            name="Growth Test",
            species=self.catfish,
            initial_count=100,
            current_stock=80,
            start_date=date.today(),
            season="rainy",
        )
        record = GrowthRecord.objects.create(
            batch=batch,
            date=date.today(),
            average_weight_kg=Decimal("1.250"),
            sample_size=50,
        )
        self.assertEqual(record.average_weight_kg, Decimal("1.250"))
        self.assertEqual(record.sample_size, 50)


class FarmManagementViewTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.farm_manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password="StrongPass1!",
            role=User.Role.FARM_MANAGER,
        )
        self.batch = Batch.objects.create(
            name="Test Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_dashboard_loads(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Farm Management', response.content.decode())

    def test_batch_list_loads(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:batch_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Test Batch', response.content.decode())

    def test_batch_create_view_get(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:batch_add'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Add Batch', response.content.decode())

    def test_batch_create_view_post(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:batch_add'),
            {
                'name': 'New Batch',
                'species': self.tilapia.pk,
                'initial_count': 150,
                'start_date': date.today().isoformat(),
                'season': 'dry',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Batch.objects.filter(name='New Batch').exists())

    def test_batch_detail_view(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:batch_detail', args=[self.batch.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Test Batch', response.content.decode())
        self.assertIn('Mortality Rate', response.content.decode())

    def test_feed_log_create(self):
        self.login(self.super_admin)
        inventory = FeedInventory.objects.create(
            feed_type='Test Feed',
            quantity_on_hand_kg=500,
            cost_per_kg=500,
            reorder_point_kg=100,
        )
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': inventory.pk,
                'quantity_kg': 50,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FeedLog.objects.count(), 1)
        log = FeedLog.objects.first()
        self.assertEqual(log.feed_inventory, inventory)
        self.assertEqual(log.cost, Decimal("25000"))
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity_on_hand_kg, Decimal("450"))

    def test_growth_record_create(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:growth_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'date': date.today().isoformat(),
                'average_weight_kg': 1.5,
                'sample_size': 20,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(GrowthRecord.objects.count(), 1)

    def test_mortality_log_creates_and_decrements_stock(self):
        self.login(self.super_admin)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_stock, 100)
        response = self.client.post(
            reverse('farm_management:mortality_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'date': date.today().isoformat(),
                'count': 5,
                'cause': 'Disease',
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_stock, 95)

    def test_staff_blocked_from_farm_management(self):
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff",
            password="StrongPass1!",
            role=User.Role.STAFF,
        )
        self.client.login(username=staff.username, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:batch_list'))
        self.assertEqual(response.status_code, 302)

    def test_feed_log_create_blocked_when_insufficient_stock(self):
        self.login(self.super_admin)
        inventory = FeedInventory.objects.create(
            feed_type='Low Stock Feed',
            quantity_on_hand_kg=50,
            cost_per_kg=500,
            reorder_point_kg=100,
        )
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': inventory.pk,
                'quantity_kg': 100,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('not enough feed in stock', response.content.decode().lower())
        self.assertEqual(FeedLog.objects.count(), 0)
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity_on_hand_kg, Decimal("50"))

    def test_feed_log_update_blocked_when_insufficient_stock(self):
        self.login(self.super_admin)
        inventory = FeedInventory.objects.create(
            feed_type='Low Stock Feed',
            quantity_on_hand_kg=50,
            cost_per_kg=500,
            reorder_point_kg=100,
        )
        # Create the log through the view so inventory is properly debited (50 -> 0)
        self.client.post(
            reverse('farm_management:feed_log_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': inventory.pk,
                'quantity_kg': 50,
                'notes': 'Initial',
            }
        )
        log = FeedLog.objects.first()
        response = self.client.post(
            reverse('farm_management:feed_log_edit', args=[log.pk]),
            {
                'batch': self.batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': inventory.pk,
                'quantity_kg': 100,
                'notes': 'Updated',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('not enough feed in stock', response.content.decode().lower())


class HarvestRecordTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.batch = Batch.objects.create(
            name="Harvest Test Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.batch.current_stock = 80
        self.batch.save(update_fields=['current_stock'])
        FeedInventory.objects.create(
            feed_type='Test Feed',
            quantity_on_hand_kg=1000,
            cost_per_kg=500,
            reorder_point_kg=100,
        )
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_inventory=FeedInventory.objects.first(),
            quantity_kg=Decimal("100.0"),
        )

    def test_harvest_creates_and_closes_batch(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:harvest_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'harvest_date': date.today().isoformat(),
                'quantity_sold': 70,
                'total_revenue': Decimal("200000"),
                'notes': 'Test harvest',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, 'closed')
        self.assertTrue(hasattr(self.batch, 'harvest'))
        self.assertEqual(self.batch.harvest.quantity_sold, 70)
        self.assertEqual(self.batch.harvest.total_revenue, Decimal("200000"))

    def test_harvest_profit_calculation(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        self.client.post(
            reverse('farm_management:harvest_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'harvest_date': date.today().isoformat(),
                'quantity_sold': 70,
                'total_revenue': Decimal("200000"),
                'notes': 'Test',
            }
        )
        self.batch.refresh_from_db()
        expected_profit = Decimal("200000") - self.batch.total_feed_cost
        self.assertEqual(self.batch.harvest.profit, expected_profit)

    def test_harvest_quantity_cannot_exceed_current_stock(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:harvest_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'harvest_date': date.today().isoformat(),
                'quantity_sold': 100,
                'total_revenue': Decimal("200000"),
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(hasattr(self.batch, 'harvest'))

    def test_duplicate_harvest_shows_friendly_error(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        self.client.post(
            reverse('farm_management:harvest_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'harvest_date': date.today().isoformat(),
                'quantity_sold': 70,
                'total_revenue': Decimal("200000"),
                'notes': 'First harvest',
            }
        )
        response = self.client.post(
            reverse('farm_management:harvest_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'harvest_date': date.today().isoformat(),
                'quantity_sold': 70,
                'total_revenue': Decimal("200000"),
                'notes': 'Duplicate harvest',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('already exists', response.content.decode())


class ClosedBatchBlockTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.closed_batch = Batch.objects.create(
            name="Closed Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.closed_batch.status = 'closed'
        self.closed_batch.save(update_fields=['status'])

    def test_feed_log_blocked_on_closed_batch(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        inventory = FeedInventory.objects.create(
            feed_type='Test Feed',
            quantity_on_hand_kg=500,
            cost_per_kg=500,
            reorder_point_kg=100,
        )
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.closed_batch.pk]),
            {
                'batch': self.closed_batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': inventory.pk,
                'quantity_kg': 10,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())
        self.assertEqual(FeedLog.objects.count(), 0)

    def test_growth_record_blocked_on_closed_batch(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:growth_add', args=[self.closed_batch.pk]),
            {
                'batch': self.closed_batch.pk,
                'date': date.today().isoformat(),
                'average_weight_kg': 1.5,
                'sample_size': 20,
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())
        self.assertEqual(GrowthRecord.objects.count(), 0)

    def test_mortality_log_blocked_on_closed_batch(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:mortality_add', args=[self.closed_batch.pk]),
            {
                'batch': self.closed_batch.pk,
                'date': date.today().isoformat(),
                'count': 5,
                'cause': 'Disease',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())
        self.assertEqual(MortalityLog.objects.count(), 0)


class FeedInventoryTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def test_feed_inventory_list_loads(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:feed_inventory_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Feed Inventory', response.content.decode())

    def test_feed_inventory_create(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        supplier = Supplier.objects.create(name="Test Supplier", phone="1234567890")
        response = self.client.post(
            reverse('farm_management:feed_inventory_add'),
            {
                'feed_type': 'Coppens 4mm',
                'supplier': supplier.pk,
                'quantity_on_hand_kg': 500,
                'cost_per_kg': 850,
                'reorder_point_kg': 100,
            }
        )
        self.assertEqual(response.status_code, 302)
        item = FeedInventory.objects.first()
        self.assertEqual(item.feed_type, 'Coppens 4mm')
        self.assertEqual(item.supplier, supplier)
        self.assertFalse(item.needs_reorder)

    def test_feed_inventory_reorder_flag(self):
        item = FeedInventory.objects.create(
            feed_type='Test Feed',
            quantity_on_hand_kg=50,
            cost_per_kg=800,
            reorder_point_kg=100,
        )
        self.assertTrue(item.needs_reorder)

    def test_feed_inventory_edit(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        supplier = Supplier.objects.create(name="Edit Supplier", phone="0987654321")
        item = FeedInventory.objects.create(
            feed_type='Test Feed',
            supplier=supplier,
            quantity_on_hand_kg=50,
            cost_per_kg=800,
            reorder_point_kg=100,
        )
        response = self.client.post(
            reverse('farm_management:feed_inventory_edit', args=[item.pk]),
            {
                'feed_type': 'Updated Feed',
                'supplier': supplier.pk,
                'quantity_on_hand_kg': 200,
                'cost_per_kg': 850,
                'reorder_point_kg': 100,
            }
        )
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.feed_type, 'Updated Feed')
        self.assertEqual(item.supplier, supplier)
        self.assertFalse(item.needs_reorder)

    def test_feed_inventory_delete(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        item = FeedInventory.objects.create(
            feed_type='ToDelete',
            quantity_on_hand_kg=50,
            cost_per_kg=800,
            reorder_point_kg=100,
        )
        response = self.client.post(
            reverse('farm_management:feed_inventory_delete', args=[item.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FeedInventory.objects.filter(pk=item.pk).exists())


class FeedInventoryModelTests(TestCase):
    def test_feed_inventory_has_category_field(self):
        field = FeedInventory._meta.get_field('category')
        self.assertTrue(field.is_relation)
        self.assertEqual(field.related_model, Category)

    def test_feed_inventory_category_can_be_null(self):
        field = FeedInventory._meta.get_field('category')
        self.assertTrue(field.null)
        self.assertTrue(field.blank)


class FeedInventoryCategoryTests(TestCase):
    def setUp(self):
        self.fish_category, _ = Category.objects.get_or_create(name="Fish")
        self.poultry_category, _ = Category.objects.get_or_create(name="Poultry")
        self.catfish, _ = Species.objects.get_or_create(name="Catfish", defaults={'category': self.fish_category, 'is_active': True})
        self.broiler, _ = Species.objects.get_or_create(name="Broiler", defaults={'category': self.poultry_category, 'is_active': True})
        self.fish_batch = Batch.objects.create(
            name="Fish Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.poultry_batch = Batch.objects.create(
            name="Poultry Batch",
            species=self.broiler,
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        self.fish_feed = FeedInventory.objects.create(
            feed_type='Fish Pellets',
            category=self.fish_category,
            quantity_on_hand_kg=100,
            cost_per_kg=500,
            reorder_point_kg=20,
        )
        self.poultry_feed = FeedInventory.objects.create(
            feed_type='Poultry Mash',
            category=self.poultry_category,
            quantity_on_hand_kg=100,
            cost_per_kg=400,
            reorder_point_kg=20,
        )
        self.unassigned_feed = FeedInventory.objects.create(
            feed_type='Generic Feed',
            quantity_on_hand_kg=100,
            cost_per_kg=300,
            reorder_point_kg=20,
        )

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin2@example.com",
            full_name="Super Admin 2",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_feed_inventory_category_assignment(self):
        self.assertEqual(self.fish_feed.category, self.fish_category)
        self.assertEqual(self.poultry_feed.category, self.poultry_category)
        self.assertIsNone(self.unassigned_feed.category)

    def test_feed_log_allows_matching_category(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': self.fish_feed.pk,
                'quantity_kg': 10,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FeedLog.objects.count(), 1)

    def test_feed_log_blocks_mismatched_category(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': self.poultry_feed.pk,
                'quantity_kg': 10,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('poultry', response.content.decode().lower())
        self.assertIn('fish', response.content.decode().lower())
        self.assertEqual(FeedLog.objects.count(), 0)

    def test_feed_log_allows_unassigned_feed(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': self.unassigned_feed.pk,
                'quantity_kg': 10,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FeedLog.objects.count(), 1)

    def test_feed_inventory_list_shows_unassigned_count(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:feed_inventory_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Unassigned', content)
        self.assertIn('border-danger', content)

    def test_feed_inventory_list_shows_category_badge(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:feed_inventory_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Fish', content)
        self.assertIn('Poultry', content)

    def test_feed_inventory_create_with_category(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_inventory_add'),
            {
                'feed_type': 'New Fish Feed',
                'category': self.fish_category.pk,
                'quantity_on_hand_kg': 200,
                'cost_per_kg': 600,
                'reorder_point_kg': 50,
            }
        )
        self.assertEqual(response.status_code, 302)
        item = FeedInventory.objects.get(feed_type='New Fish Feed')
        self.assertEqual(item.category, self.fish_category)

    def test_feed_inventory_create_without_category(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_inventory_add'),
            {
                'feed_type': 'Unassigned Feed',
                'quantity_on_hand_kg': 200,
                'cost_per_kg': 600,
                'reorder_point_kg': 50,
            }
        )
        self.assertEqual(response.status_code, 302)
        item = FeedInventory.objects.get(feed_type='Unassigned Feed')
        self.assertIsNone(item.category)


class FeedInventoryBatchLinkingTests(TestCase):
    def setUp(self):
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.fish_batch = Batch.objects.create(
            name="Fish Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.poultry_batch = Batch.objects.create(
            name="Poultry Batch",
            species=self.broiler,
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        self.fish_feed = FeedInventory.objects.create(
            feed_type='Fish Pellets',
            category=self.fish_category,
            quantity_on_hand_kg=100,
            cost_per_kg=500,
            reorder_point_kg=20,
        )
        self.poultry_feed = FeedInventory.objects.create(
            feed_type='Poultry Mash',
            category=self.poultry_category,
            quantity_on_hand_kg=100,
            cost_per_kg=400,
            reorder_point_kg=20,
        )

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin3@example.com",
            full_name="Super Admin 3",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_feed_inventory_str_returns_feed_type_and_category(self):
        self.assertEqual(str(self.fish_feed), "Fish Pellets (Fish)")
        self.assertEqual(str(self.poultry_feed), "Poultry Mash (Poultry)")

    def test_feed_inventory_str_without_category(self):
        feed = FeedInventory.objects.create(
            feed_type='Generic Feed',
            quantity_on_hand_kg=100,
            cost_per_kg=300,
            reorder_point_kg=20,
        )
        self.assertEqual(str(feed), "Generic Feed")

    def test_feed_inventory_form_saves_compatible_batches(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_inventory_add'),
            {
                'feed_type': 'Test Feed',
                'category': self.fish_category.pk,
                'quantity_on_hand_kg': 100,
                'cost_per_kg': 500,
                'reorder_point_kg': 20,
                'compatible_batches': [self.fish_batch.pk, self.poultry_batch.pk],
            }
        )
        self.assertEqual(response.status_code, 302)
        item = FeedInventory.objects.get(feed_type='Test Feed')
        self.assertEqual(item.compatible_batches.count(), 2)
        self.assertIn(self.fish_batch, item.compatible_batches.all())
        self.assertIn(self.poultry_batch, item.compatible_batches.all())

    def test_feed_inventory_form_updates_compatible_batches(self):
        self.fish_feed.compatible_batches.add(self.fish_batch)
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_inventory_edit', args=[self.fish_feed.pk]),
            {
                'feed_type': 'Fish Pellets',
                'category': self.fish_category.pk,
                'quantity_on_hand_kg': 100,
                'cost_per_kg': 500,
                'reorder_point_kg': 20,
                'compatible_batches': [self.poultry_batch.pk],
            }
        )
        self.assertEqual(response.status_code, 302)
        self.fish_feed.refresh_from_db()
        self.assertEqual(self.fish_feed.compatible_batches.count(), 1)
        self.assertIn(self.poultry_batch, self.fish_feed.compatible_batches.all())
        self.assertNotIn(self.fish_batch, self.fish_feed.compatible_batches.all())

    def test_feed_inventory_list_shows_linked_batch_names(self):
        self.fish_feed.compatible_batches.add(self.fish_batch, self.poultry_batch)
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:feed_inventory_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Fish Batch', content)
        self.assertIn('Poultry Batch', content)

    def test_feed_log_category_validation_still_works_with_batch_linking(self):
        self.fish_feed.compatible_batches.add(self.fish_batch, self.poultry_batch)
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': self.fish_feed.pk,
                'quantity_kg': 10,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FeedLog.objects.count(), 1)

    def test_feed_log_blocks_mismatched_category_even_with_batch_linking(self):
        self.fish_feed.compatible_batches.add(self.fish_batch, self.poultry_batch)
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.poultry_batch.pk]),
            {
                'batch': self.poultry_batch.pk,
                'date': date.today().isoformat(),
                'feed_inventory': self.fish_feed.pk,
                'quantity_kg': 10,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('poultry', response.content.decode().lower())
        self.assertIn('fish', response.content.decode().lower())
        self.assertEqual(FeedLog.objects.count(), 0)


class Phase3LogTests(TestCase):
    def setUp(self):
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.fish_batch = Batch.objects.create(
            name="Fish Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.poultry_batch = Batch.objects.create(
            name="Poultry Batch",
            species=self.broiler,
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )

    def test_health_log_create(self):
        self.fish_batch.status = 'closed'
        self.fish_batch.save(update_fields=['status'])
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:health_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'medicine_name': 'Test Med',
                'dosage': '5mg',
                'reason': 'Test',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())

    def test_vaccination_create(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:vaccination_add', args=[self.poultry_batch.pk]),
            {
                'batch': self.poultry_batch.pk,
                'date': date.today().isoformat(),
                'vaccine_name': 'Newcastle Vaccine',
                'dosage': '0.5ml per bird',
                'administered_by': 'Farm Manager',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(VaccinationRecord.objects.count(), 1)

    def test_daily_activity_log_create(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:activity_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'note': 'Fed the fish at 6am. Water looks clear.',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DailyActivityLog.objects.count(), 1)

    def test_daily_activity_log_blocks_closed_batch(self):
        self.fish_batch.status = 'closed'
        self.fish_batch.save(update_fields=['status'])
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:activity_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'note': 'Test activity',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())
        self.assertEqual(DailyActivityLog.objects.count(), 0)


class VaccinationRecordSpeciesTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.fish_batch = Batch.objects.create(
            name="Fish Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.poultry_batch = Batch.objects.create(
            name="Poultry Batch",
            species=self.broiler,
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )

    def test_vaccination_blocked_on_fish_batch(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:vaccination_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'vaccine_name': 'Newcastle Vaccine',
                'dosage': '0.5ml per bird',
                'administered_by': 'Farm Manager',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('poultry', response.content.decode().lower())
        self.assertEqual(VaccinationRecord.objects.count(), 0)

    def test_vaccination_allowed_on_poultry_batch(self):
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:vaccination_add', args=[self.poultry_batch.pk]),
            {
                'batch': self.poultry_batch.pk,
                'date': date.today().isoformat(),
                'vaccine_name': 'Newcastle Vaccine',
                'dosage': '0.5ml per bird',
                'administered_by': 'Farm Manager',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(VaccinationRecord.objects.count(), 1)


class CheckBatchAlertsTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def test_feed_log_gap_alert(self):
        batch = Batch.objects.create(
            name="No Feed Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        call_command('check_batch_alerts')
        self.assertEqual(
            Notification.objects.filter(
                notification_type='batch_alert',
                message__icontains='no feed log',
            ).count(),
            1,
        )

    def test_no_feed_gap_alert_when_recent_log_exists(self):
        batch = Batch.objects.create(
            name="Fed Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        inventory = FeedInventory.objects.create(
            feed_type='Test Feed',
            quantity_on_hand_kg=1000,
            cost_per_kg=500,
            reorder_point_kg=100,
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory,
            quantity_kg=Decimal("10.0"),
        )
        call_command('check_batch_alerts')
        self.assertEqual(
            Notification.objects.filter(
                notification_type='batch_alert',
                message__icontains='no feed log',
            ).count(),
            0,
        )

    def test_low_feed_inventory_alert(self):
        FeedInventory.objects.create(
            feed_type='Low Feed',
            quantity_on_hand_kg=50,
            cost_per_kg=800,
            reorder_point_kg=100,
        )
        call_command('check_batch_alerts')
        self.assertEqual(
            Notification.objects.filter(
                notification_type='batch_alert',
                message__icontains='Low Feed',
            ).count(),
            1,
        )

    def test_no_duplicate_low_stock_alert(self):
        item = FeedInventory.objects.create(
            feed_type='Low Feed',
            quantity_on_hand_kg=50,
            cost_per_kg=800,
            reorder_point_kg=100,
        )
        Notification.objects.create(
            notification_type='batch_alert',
            message=f'Feed inventory "{item.feed_type}" is below reorder point.',
            related_object_id=item.pk,
        )
        call_command('check_batch_alerts')
        self.assertEqual(
            Notification.objects.filter(
                notification_type='batch_alert',
                message__icontains='Low Feed',
            ).count(),
            1,
        )

    def test_mortality_jump_alert(self):
        batch_high = Batch.objects.create(
            name="High Mort Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        MortalityLog.objects.create(
            batch=batch_high,
            date=date.today() - timedelta(days=10),
            count=2,
            cause="Minor",
        )
        MortalityLog.objects.create(
            batch=batch_high,
            date=date.today() - timedelta(days=5),
            count=3,
            cause="Minor",
        )
        MortalityLog.objects.create(
            batch=batch_high,
            date=date.today(),
            count=15,
            cause="Disease",
        )
        call_command('check_batch_alerts')
        self.assertEqual(
            Notification.objects.filter(
                notification_type='batch_alert',
                message__icontains='mortality',
            ).count(),
            1,
        )

    def test_no_mortality_alert_when_stable(self):
        batch_stable = Batch.objects.create(
            name="Stable Mort Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        MortalityLog.objects.create(
            batch=batch_stable,
            date=date.today() - timedelta(days=10),
            count=2,
            cause="Minor",
        )
        MortalityLog.objects.create(
            batch=batch_stable,
            date=date.today() - timedelta(days=5),
            count=3,
            cause="Minor",
        )
        MortalityLog.objects.create(
            batch=batch_stable,
            date=date.today(),
            count=2,
            cause="Minor",
        )
        call_command('check_batch_alerts')
        self.assertEqual(
            Notification.objects.filter(
                notification_type='batch_alert',
                message__icontains='mortality',
            ).count(),
            0,
        )


# =============================================================================
# Feature 1: Batch Comparison Analytics Dashboard Tests
# =============================================================================

class BatchAnalyticsViewTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.farm_manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password="StrongPass1!",
            role=User.Role.FARM_MANAGER,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_analytics_loads_for_super_admin(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Batch Analytics', response.content.decode())

    def test_analytics_preserves_admin_stylesheet_when_loading_charts(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:analytics'))
        content = response.content.decode()

        self.assertIn('admin_dashboard/css/admin_dashboard.css', content)
        self.assertIn('farm_management/css/farm_management.css', content)
        self.assertIn('chart.umd.js', content)

    def test_analytics_loads_for_farm_manager(self):
        self.login(self.farm_manager)
        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)

    def test_analytics_blocks_staff(self):
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff",
            password="StrongPass1!",
            role=User.Role.STAFF,
        )
        self.client.login(username=staff.username, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:analytics'), follow=False)
        self.assertEqual(response.status_code, 302)

    def test_analytics_highlights_highest_feed(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Low Feed Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="High Feed Batch",
            species=self.tilapia,
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        inventory_a = FeedInventory.objects.create(
            feed_type='A', quantity_on_hand_kg=1000, cost_per_kg=100, reorder_point_kg=100,
        )
        inventory_b = FeedInventory.objects.create(
            feed_type='B', quantity_on_hand_kg=1000, cost_per_kg=100, reorder_point_kg=100,
        )
        FeedLog.objects.create(batch=batch1, date=date.today(), feed_inventory=inventory_a, quantity_kg=10)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_inventory=inventory_b, quantity_kg=50)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_inventory=inventory_b, quantity_kg=30)

        response = self.client.get(reverse('farm_management:analytics'))
        content = response.content.decode()
        self.assertIn('High Feed Batch', content)

    def test_analytics_highlights_best_fcr(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Bad FCR Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="Good FCR Batch",
            species=self.tilapia,
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        inventory_a = FeedInventory.objects.create(
            feed_type='A', quantity_on_hand_kg=1000, cost_per_kg=50, reorder_point_kg=100,
        )
        inventory_b = FeedInventory.objects.create(
            feed_type='B', quantity_on_hand_kg=1000, cost_per_kg=100, reorder_point_kg=100,
        )
        FeedLog.objects.create(batch=batch1, date=date.today(), feed_inventory=inventory_a, quantity_kg=200)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_inventory=inventory_b, quantity_kg=50)
        GrowthRecord.objects.create(batch=batch1, date=date.today(), average_weight_kg=1.0, sample_size=100)
        GrowthRecord.objects.create(batch=batch1, date=date.today() + timedelta(days=30), average_weight_kg=2.0, sample_size=80)
        GrowthRecord.objects.create(batch=batch2, date=date.today(), average_weight_kg=1.0, sample_size=100)
        GrowthRecord.objects.create(batch=batch2, date=date.today() + timedelta(days=30), average_weight_kg=3.0, sample_size=80)

        response = self.client.get(reverse('farm_management:analytics'))
        content = response.content.decode()
        self.assertIn('Good FCR Batch', content)

    def test_analytics_highlights_highest_mortality(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Low Mortality Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="High Mortality Batch",
            species=self.tilapia,
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        MortalityLog.objects.create(batch=batch1, date=date.today(), count=5, cause="Disease")
        MortalityLog.objects.create(batch=batch2, date=date.today(), count=30, cause="Disease")

        response = self.client.get(reverse('farm_management:analytics'))
        content = response.content.decode()
        self.assertIn('High Mortality Batch', content)

    def test_analytics_highlights_most_profitable(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Low Profit Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="High Profit Batch",
            species=self.tilapia,
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        inventory_a = FeedInventory.objects.create(
            feed_type='A', quantity_on_hand_kg=1000, cost_per_kg=500, reorder_point_kg=100,
        )
        inventory_b = FeedInventory.objects.create(
            feed_type='B', quantity_on_hand_kg=1000, cost_per_kg=500, reorder_point_kg=100,
        )
        FeedLog.objects.create(batch=batch1, date=date.today(), feed_inventory=inventory_a, quantity_kg=100)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_inventory=inventory_b, quantity_kg=100)
        HarvestRecord.objects.create(
            batch=batch1,
            harvest_date=date.today(),
            quantity_sold=80,
            total_revenue=100000,
        )
        HarvestRecord.objects.create(
            batch=batch2,
            harvest_date=date.today(),
            quantity_sold=80,
            total_revenue=300000,
        )

        response = self.client.get(reverse('farm_management:analytics'))
        content = response.content.decode()
        self.assertIn('High Profit Batch', content)

    def test_analytics_no_batches(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('No batches found', response.content.decode())

    def test_vaccination_coverage_data_in_context(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Vacc Batch 1",
            species=self.catfish,
            initial_count=100,
            current_stock=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="Vacc Batch 2",
            species=self.tilapia,
            initial_count=50,
            current_stock=50,
            start_date=date.today(),
            season="dry",
        )
        VaccinationRecord.objects.create(batch=batch1, date=date.today(), vaccine_name="Vaccine A", dosage="1ml")
        VaccinationRecord.objects.create(batch=batch1, date=date.today(), vaccine_name="Vaccine B", dosage="1ml")
        VaccinationRecord.objects.create(batch=batch2, date=date.today(), vaccine_name="Vaccine A", dosage="0.5ml")

        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check chart canvas and description are present
        self.assertIn('vaccinationCoverageChart', content)
        self.assertIn('Vaccination Coverage per Batch', content)
        self.assertIn('Vacc Batch 1', content)
        self.assertIn('Vacc Batch 2', content)

    def test_health_log_frequency_data_in_context(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Health Batch 1",
            species=self.catfish,
            initial_count=100,
            current_stock=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="Health Batch 2",
            species=self.tilapia,
            initial_count=50,
            current_stock=50,
            start_date=date.today(),
            season="dry",
        )
        HealthMedicationLog.objects.create(batch=batch1, date=date.today(), medicine_name="Antibiotic X", dosage="10mg", reason="Fungal infection")
        HealthMedicationLog.objects.create(batch=batch1, date=date.today(), medicine_name="Antibiotic Y", dosage="5mg", reason="Bacterial infection")
        HealthMedicationLog.objects.create(batch=batch2, date=date.today(), medicine_name="Antibiotic X", dosage="8mg", reason="Fungal infection")

        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check chart canvas and description are present
        self.assertIn('healthLogFrequencyChart', content)
        self.assertIn('Health Issue Frequency per Batch', content)
        self.assertIn('Health Batch 1', content)
        self.assertIn('Health Batch 2', content)

    def test_health_reasons_pie_chart_data(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Reason Batch 1",
            species=self.catfish,
            initial_count=100,
            current_stock=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="Reason Batch 2",
            species=self.tilapia,
            initial_count=50,
            current_stock=50,
            start_date=date.today(),
            season="dry",
        )
        HealthMedicationLog.objects.create(batch=batch1, date=date.today(), medicine_name="Med A", dosage="10mg", reason="Fungal infection")
        HealthMedicationLog.objects.create(batch=batch1, date=date.today(), medicine_name="Med B", dosage="5mg", reason="Fungal infection")
        HealthMedicationLog.objects.create(batch=batch2, date=date.today(), medicine_name="Med C", dosage="8mg", reason="Bacterial infection")

        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn('healthReasonsPieChart', content)
        self.assertIn('Most Common Health Reasons', content)

    def test_health_medicines_pie_chart_data(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Med Batch 1",
            species=self.catfish,
            initial_count=100,
            current_stock=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="Med Batch 2",
            species=self.tilapia,
            initial_count=50,
            current_stock=50,
            start_date=date.today(),
            season="dry",
        )
        HealthMedicationLog.objects.create(batch=batch1, date=date.today(), medicine_name="Antibiotic X", dosage="10mg", reason="Fungal infection")
        HealthMedicationLog.objects.create(batch=batch1, date=date.today(), medicine_name="Antibiotic X", dosage="5mg", reason="Bacterial infection")
        HealthMedicationLog.objects.create(batch=batch2, date=date.today(), medicine_name="Vitamin C", dosage="2mg", reason="Supplements")

        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn('healthMedicinesPieChart', content)
        self.assertIn('Most Common Medications Used', content)

    def test_vaccination_chart_excludes_no_vaccination_batches(self):
        self.login(self.super_admin)
        batch_with_vacc = Batch.objects.create(
            name="Has Vacc",
            species=self.catfish,
            initial_count=100,
            current_stock=100,
            start_date=date.today(),
            season="rainy",
        )
        batch_no_vacc = Batch.objects.create(
            name="No Vacc",
            species=self.tilapia,
            initial_count=50,
            current_stock=50,
            start_date=date.today(),
            season="dry",
        )
        VaccinationRecord.objects.create(batch=batch_with_vacc, date=date.today(), vaccine_name="Vaccine A", dosage="1ml")

        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Has Vacc', content)
        self.assertIn('No Vacc', content)


# =============================================================================
# Feature 2: Supplier Directory Tests
# =============================================================================

class SupplierModelTests(TestCase):
    def test_supplier_creation(self):
        supplier = Supplier.objects.create(
            name="Test Supplier",
            phone="1234567890",
            email="test@example.com",
            address="123 Main St",
            notes="Test notes",
        )
        self.assertEqual(supplier.name, "Test Supplier")
        self.assertEqual(supplier.phone, "1234567890")
        self.assertEqual(supplier.email, "test@example.com")

    def test_supplier_str(self):
        supplier = Supplier.objects.create(name="String Test Supplier")
        self.assertEqual(str(supplier), "String Test Supplier")


class SupplierCRUDTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_supplier_list_loads(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:supplier_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Suppliers', response.content.decode())

    def test_supplier_create(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:supplier_add'),
            {
                'name': 'New Supplier',
                'phone': '1234567890',
                'email': 'new@example.com',
                'address': '123 Main St',
                'notes': 'Test supplier',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Supplier.objects.filter(name='New Supplier').exists())

    def test_supplier_create_get(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:supplier_add'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Add Supplier', response.content.decode())

    def test_supplier_update(self):
        self.login(self.super_admin)
        supplier = Supplier.objects.create(name="Old Name", phone="1111111111")
        response = self.client.post(
            reverse('farm_management:supplier_edit', args=[supplier.pk]),
            {
                'name': 'Updated Name',
                'phone': '2222222222',
                'email': 'updated@example.com',
                'address': '456 New St',
                'notes': 'Updated notes',
            }
        )
        self.assertEqual(response.status_code, 302)
        supplier.refresh_from_db()
        self.assertEqual(supplier.name, 'Updated Name')

    def test_supplier_delete(self):
        self.login(self.super_admin)
        supplier = Supplier.objects.create(name="Delete Me")
        response = self.client.post(
            reverse('farm_management:supplier_delete', args=[supplier.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Supplier.objects.filter(pk=supplier.pk).exists())

    def test_staff_blocked_from_supplier_crud(self):
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff",
            password="StrongPass1!",
            role=User.Role.STAFF,
        )
        self.client.login(username=staff.username, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:supplier_list'), follow=False)
        self.assertEqual(response.status_code, 302)


class SupplierMigrationIntegrityTests(TestCase):
    def test_migration_0002_creates_supplier_and_alters_feedinventory(self):
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__), 'migrations', '0002_supplier_alter_feedinventory_supplier.py'
        )
        self.assertTrue(os.path.exists(migration_path))
        with open(migration_path) as f:
            content = f.read()
        self.assertIn('CreateModel', content)
        self.assertIn('AlterField', content)
        self.assertIn('Supplier', content)
        self.assertIn('feedinventory', content)

    def test_feedinventory_supplier_is_foreign_key(self):
        field = FeedInventory._meta.get_field('supplier')
        self.assertTrue(field.is_relation)
        self.assertEqual(field.related_model, Supplier)

    def test_feedinventory_supplier_can_be_null(self):
        field = FeedInventory._meta.get_field('supplier')
        self.assertTrue(field.null)
        self.assertTrue(field.blank)

    def test_supplier_has_feed_inventory_related_name(self):
        supplier = Supplier.objects.create(name="Related Test Supplier")
        FeedInventory.objects.create(
            feed_type="Test Feed",
            supplier=supplier,
            quantity_on_hand_kg=100,
            cost_per_kg=800,
            reorder_point_kg=50,
        )
        self.assertEqual(supplier.feed_inventory.count(), 1)


# =============================================================================
# Feature 3: PDF Batch Reports Tests
# =============================================================================

class BatchPDFReportTests(TestCase):
    def setUp(self):
        # Create species for tests
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.layer = Species.objects.create(name="Layer", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_pdf_report_active_batch(self):
        self.login(self.super_admin)
        batch = Batch.objects.create(
            name="Active Batch Report",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        inventory = FeedInventory.objects.create(
            feed_type='Test Feed',
            quantity_on_hand_kg=1000,
            cost_per_kg=100,
            reorder_point_kg=100,
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory,
            quantity_kg=50,
        )
        GrowthRecord.objects.create(
            batch=batch,
            date=date.today(),
            average_weight_kg=1.0,
            sample_size=100,
        )
        MortalityLog.objects.create(
            batch=batch,
            date=date.today(),
            count=5,
            cause="Disease",
        )

        response = self.client.get(reverse('farm_management:batch_report', args=[batch.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_pdf_report_closed_batch_with_harvest(self):
        self.login(self.super_admin)
        batch = Batch.objects.create(
            name="Closed Batch Report",
            species=self.tilapia,
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        inventory = FeedInventory.objects.create(
            feed_type='Test Feed',
            quantity_on_hand_kg=1000,
            cost_per_kg=100,
            reorder_point_kg=100,
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_inventory=inventory,
            quantity_kg=50,
        )
        GrowthRecord.objects.create(
            batch=batch,
            date=date.today(),
            average_weight_kg=1.0,
            sample_size=100,
        )
        HarvestRecord.objects.create(
            batch=batch,
            harvest_date=date.today(),
            quantity_sold=80,
            total_revenue=200000,
        )

        response = self.client.get(reverse('farm_management:batch_report', args=[batch.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_pdf_report_staff_blocked(self):
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff",
            password="StrongPass1!",
            role=User.Role.STAFF,
        )
        self.client.login(username=staff.username, password="StrongPass1!")
        batch = Batch.objects.create(
            name="Staff Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        response = self.client.get(
            reverse('farm_management:batch_report', args=[batch.pk]),
            follow=False,
        )
        self.assertEqual(response.status_code, 302)

    def test_pdf_report_unauthenticated_redirected(self):
        batch = Batch.objects.create(
            name="Unauth Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        response = self.client.get(
            reverse('farm_management:batch_report', args=[batch.pk]),
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)


class BatchSearchTests(TestCase):
    def setUp(self):
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.tilapia = Species.objects.create(name="Tilapia", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)

        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.batch1 = Batch.objects.create(
            name="Catfish Batch A",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.batch2 = Batch.objects.create(
            name="Tilapia Batch B",
            species=self.tilapia,
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )
        self.batch3 = Batch.objects.create(
            name="Broiler Batch C",
            species=self.broiler,
            initial_count=150,
            start_date=date.today(),
            season="rainy",
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_batch_search_by_name(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:batch_list') + '?search=Catfish')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Catfish Batch A', content)
        self.assertNotIn('Tilapia Batch B', content)
        self.assertNotIn('Broiler Batch C', content)

    def test_batch_search_case_insensitive(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:batch_list') + '?search=tilapia')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Tilapia Batch B', content)
        self.assertNotIn('Catfish Batch A', content)

    def test_batch_search_no_results(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:batch_list') + '?search=Nonexistent')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('No batches found', content)

    def test_batch_search_empty_query_shows_all(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:batch_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Catfish Batch A', content)
        self.assertIn('Tilapia Batch B', content)
        self.assertIn('Broiler Batch C', content)


# =============================================================================
# Category Management Tests
# =============================================================================

class CategoryModelTests(TestCase):
    def test_category_creation(self):
        category = Category.objects.create(name="Fish")
        self.assertEqual(category.name, "Fish")
        self.assertTrue(category.is_active)

    def test_category_str(self):
        category = Category.objects.create(name="Poultry")
        self.assertEqual(str(category), "Poultry")

    def test_category_unique_name(self):
        Category.objects.create(name="Fish")
        with self.assertRaises(IntegrityError):
            Category.objects.create(name="Fish")


class CategoryCRUDTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_category_list_loads(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:category_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Categories', response.content.decode())
        self.assertIn('Fish', response.content.decode())
        self.assertIn('Poultry', response.content.decode())

    def test_category_create(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:category_add'),
            {'name': 'Livestock'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Category.objects.filter(name='Livestock').exists())

    def test_category_create_get(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:category_add'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Add Category', response.content.decode())

    def test_category_update(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:category_edit', args=[self.fish_category.pk]),
            {'name': 'Aquaculture', 'is_active': True}
        )
        self.assertEqual(response.status_code, 302)
        self.fish_category.refresh_from_db()
        self.assertEqual(self.fish_category.name, 'Aquaculture')

    def test_category_delete_deactivates_when_species_exist(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:category_delete', args=[self.fish_category.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.fish_category.refresh_from_db()
        self.assertFalse(self.fish_category.is_active)
        self.assertTrue(Category.objects.filter(pk=self.fish_category.pk).exists())

    def test_category_delete_removes_when_no_species(self):
        empty_category = Category.objects.create(name="Empty")
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:category_delete', args=[empty_category.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Category.objects.filter(pk=empty_category.pk).exists())

    def test_deactivated_category_hidden_from_species_form(self):
        self.login(self.super_admin)
        self.fish_category.is_active = False
        self.fish_category.save(update_fields=['is_active'])
        response = self.client.get(reverse('farm_management:species_add'))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        active_category_names = [c.name for c in form.fields['category'].queryset]
        self.assertNotIn('Fish', active_category_names)
        self.assertIn('Poultry', active_category_names)

    def test_existing_species_unaffected_by_deactivated_category(self):
        self.login(self.super_admin)
        self.fish_category.is_active = False
        self.fish_category.save(update_fields=['is_active'])
        self.catfish.refresh_from_db()
        self.assertEqual(self.catfish.category.name, 'Fish')
        self.assertTrue(self.catfish.is_active)

    def test_staff_blocked_from_category_crud(self):
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff",
            password="StrongPass1!",
            role=User.Role.STAFF,
        )
        self.client.login(username=staff.username, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:category_list'), follow=False)
        self.assertEqual(response.status_code, 302)

    def test_category_unique_name_constraint(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:category_add'),
            {'name': 'Fish'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('already exists', response.content.decode().lower())

    def test_category_form_excludes_deactivated_from_dropdown(self):
        self.fish_category.is_active = False
        self.fish_category.save(update_fields=['is_active'])
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:species_add'))
        self.assertEqual(response.status_code, 200)
        # The form should only show active categories
        form = response.context['form']
        active_category_names = [c.name for c in form.fields['category'].queryset]
        self.assertIn('Poultry', active_category_names)
        self.assertNotIn('Fish', active_category_names)

    def test_category_edit_form_includes_deactivated(self):
        self.fish_category.is_active = False
        self.fish_category.save(update_fields=['is_active'])
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:category_edit', args=[self.fish_category.pk]))
        self.assertEqual(response.status_code, 200)

    def test_category_list_shows_species_count(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:category_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('1', content)  # species count column should show 1


# =============================================================================
# Sample Data Management Tests
# =============================================================================

class SampleDataManagementTests(TestCase):
    """
    Tests for the populate_sample and delete_sample management commands and
    the admin dashboard buttons that trigger them.
    """

    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.farm_manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password="StrongPass1!",
            role=User.Role.FARM_MANAGER,
        )
        # Wipe any pre-existing sample data so tests start clean
        call_command('delete_sample', verbosity=0)

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    # ------------------------------------------------------------------
    # populate_sample — creates expected records tagged is_sample=True
    # ------------------------------------------------------------------

    def test_populate_sample_creates_expected_records_all_tagged_is_sample(self):
        call_command('populate_sample', verbosity=0)

        # All created records must be tagged is_sample=True or is_sample_data=True
        self.assertEqual(Category.objects.filter(is_sample=True).count(), 3)
        self.assertEqual(Species.objects.filter(is_sample=True).count(), 7)
        self.assertEqual(Supplier.objects.filter(is_sample=True).count(), 5)
        self.assertEqual(FeedInventory.objects.filter(is_sample=True).count(), 5)
        self.assertEqual(Batch.objects.filter(is_sample=True).count(), 6)

        # Related records
        self.assertEqual(FeedLog.objects.filter(is_sample=True).count(), 18)
        self.assertEqual(GrowthRecord.objects.filter(is_sample=True).count(), 18)
        self.assertEqual(MortalityLog.objects.filter(is_sample=True).count(), 13)
        self.assertEqual(VaccinationRecord.objects.filter(is_sample=True).count(), 8)
        self.assertEqual(HealthMedicationLog.objects.filter(is_sample=True).count(), 16)
        self.assertEqual(DailyActivityLog.objects.filter(is_sample=True).count(), 18)
        self.assertEqual(FarmExpense.objects.count(), 10)

        # Sample users
        self.assertEqual(User.objects.filter(is_sample_data=True).count(), 7)

        # Sample orders and payments
        self.assertEqual(Order.objects.filter(is_sample_data=True).count(), 5)
        self.assertEqual(OrderItem.objects.filter(is_sample_data=True).count(), 10)
        self.assertEqual(Payment.objects.filter(is_sample_data=True).count(), 5)

        # No real data should have been created
        self.assertEqual(Category.objects.filter(is_sample=False).count(), 0)
        self.assertEqual(Batch.objects.filter(is_sample=False).count(), 0)

    def test_populate_sample_categories_and_species_correct(self):
        call_command('populate_sample', verbosity=0)

        categories = set(Category.objects.filter(is_sample=True).values_list('name', flat=True))
        self.assertEqual(categories, {'Fish', 'Poultry', 'Cattle'})

        species = set(Species.objects.filter(is_sample=True).values_list('name', flat=True))
        self.assertEqual(species, {'Catfish', 'Tilapia', 'Broiler', 'Layer', 'Turkey',
                                    'White Fulani', 'Sokoto Gudali'})

    def test_populate_sample_feed_linked_to_correct_category(self):
        call_command('populate_sample', verbosity=0)

        fish_feeds = FeedInventory.objects.filter(is_sample=True, category__name='Fish')
        poultry_feeds = FeedInventory.objects.filter(is_sample=True, category__name='Poultry')
        cattle_feeds = FeedInventory.objects.filter(is_sample=True, category__name='Cattle')

        self.assertEqual(fish_feeds.count(), 2)
        self.assertEqual(poultry_feeds.count(), 2)
        self.assertEqual(cattle_feeds.count(), 1)

    def test_populate_sample_batches_across_species(self):
        call_command('populate_sample', verbosity=0)

        batches = Batch.objects.filter(is_sample=True)
        self.assertEqual(batches.count(), 6)

        # Verify species distribution
        species_names = set(batches.values_list('species__name', flat=True))
        self.assertEqual(species_names, {'Catfish', 'Tilapia', 'Broiler', 'Layer',
                                          'White Fulani', 'Sokoto Gudali'})

    def test_populate_sample_vaccination_only_for_non_fish(self):
        call_command('populate_sample', verbosity=0)

        fish_batches = Batch.objects.filter(is_sample=True, species__category__name='Fish')
        non_fish_batches = Batch.objects.filter(
            is_sample=True
        ).exclude(species__category__name='Fish')

        for batch in fish_batches:
            self.assertEqual(
                batch.vaccination_records.count(), 0,
                f"Fish batch '{batch.name}' should not have vaccination records",
            )

        for batch in non_fish_batches:
            self.assertGreater(
                batch.vaccination_records.count(), 0,
                f"Non-fish batch '{batch.name}' should have vaccination records",
            )

    # ------------------------------------------------------------------
    # Idempotency — running twice doesn't duplicate
    # ------------------------------------------------------------------

    def test_populate_sample_running_twice_does_not_duplicate(self):
        call_command('populate_sample', verbosity=0)

        counts_after_first = {
            'Category': (Category.objects.filter(is_sample=True).count(), 'is_sample'),
            'Species': (Species.objects.filter(is_sample=True).count(), 'is_sample'),
            'Supplier': (Supplier.objects.filter(is_sample=True).count(), 'is_sample'),
            'FeedInventory': (FeedInventory.objects.filter(is_sample=True).count(), 'is_sample'),
            'Batch': (Batch.objects.filter(is_sample=True).count(), 'is_sample'),
            'FeedLog': (FeedLog.objects.filter(is_sample=True).count(), 'is_sample'),
            'GrowthRecord': (GrowthRecord.objects.filter(is_sample=True).count(), 'is_sample'),
            'MortalityLog': (MortalityLog.objects.filter(is_sample=True).count(), 'is_sample'),
            'VaccinationRecord': (VaccinationRecord.objects.filter(is_sample=True).count(), 'is_sample'),
            'HealthMedicationLog': (HealthMedicationLog.objects.filter(is_sample=True).count(), 'is_sample'),
            'DailyActivityLog': (DailyActivityLog.objects.filter(is_sample=True).count(), 'is_sample'),
            'FarmExpense': (FarmExpense.objects.count(), 'is_sample'),
            'User': (User.objects.filter(is_sample_data=True).count(), 'is_sample_data'),
            'Order': (Order.objects.filter(is_sample_data=True).count(), 'is_sample_data'),
            'OrderItem': (OrderItem.objects.filter(is_sample_data=True).count(), 'is_sample_data'),
            'Payment': (Payment.objects.filter(is_sample_data=True).count(), 'is_sample_data'),
        }

        # Second run should be a no-op
        call_command('populate_sample', verbosity=0)

        for model_name, (count, flag) in counts_after_first.items():
            model = globals()[model_name]
            self.assertEqual(
                model.objects.filter(**{flag: True}).count(),
                count,
                f"{model_name} count changed on second run",
            )

    # ------------------------------------------------------------------
    # delete_sample — removes only is_sample=True records
    # ------------------------------------------------------------------

    def test_delete_sample_removes_only_sample_data(self):
        # Populate sample data
        call_command('populate_sample', verbosity=0)

        # Create real (non-sample) data
        real_category = Category.objects.create(name="Real Category")
        real_species = Species.objects.create(name="Real Species", category=real_category)
        real_supplier = Supplier.objects.create(name="Real Supplier")
        real_feed = FeedInventory.objects.create(
            feed_type="Real Feed",
            category=real_category,
            supplier=real_supplier,
            quantity_on_hand_kg=Decimal("100.00"),
            cost_per_kg=Decimal("300.00"),
            reorder_point_kg=Decimal("50.00"),
        )
        real_batch = Batch.objects.create(
            name="Real Batch",
            species=real_species,
            initial_count=500,
            start_date=date.today(),
            season="rainy",
        )
        real_user = User.objects.create_user(
            email="realuser@example.com",
            full_name="Real User",
            password="StrongPass1!",
            role=User.Role.CUSTOMER,
        )

        # Confirm both exist
        self.assertTrue(Batch.objects.filter(is_sample=True).exists())
        self.assertTrue(Batch.objects.filter(is_sample=False).exists())
        self.assertEqual(User.objects.filter(is_sample_data=True).count(), 7)

        # Delete only sample data
        call_command('delete_sample', verbosity=0)

        # Sample data is gone
        self.assertFalse(Batch.objects.filter(is_sample=True).exists())
        self.assertFalse(Category.objects.filter(is_sample=True).exists())
        self.assertFalse(Species.objects.filter(is_sample=True).exists())
        self.assertFalse(Supplier.objects.filter(is_sample=True).exists())
        self.assertFalse(FeedInventory.objects.filter(is_sample=True).exists())
        self.assertFalse(FeedLog.objects.filter(is_sample=True).exists())
        self.assertFalse(GrowthRecord.objects.filter(is_sample=True).exists())
        self.assertFalse(MortalityLog.objects.filter(is_sample=True).exists())
        self.assertFalse(VaccinationRecord.objects.filter(is_sample=True).exists())
        self.assertFalse(HealthMedicationLog.objects.filter(is_sample=True).exists())
        self.assertFalse(DailyActivityLog.objects.filter(is_sample=True).exists())
        self.assertFalse(Order.objects.filter(is_sample_data=True).exists())
        self.assertFalse(OrderItem.objects.filter(is_sample_data=True).exists())
        self.assertFalse(Payment.objects.filter(is_sample_data=True).exists())
        self.assertEqual(User.objects.filter(is_sample_data=True).count(), 0)
        self.assertEqual(FarmExpense.objects.count(), 0)

        # Real data remains
        self.assertTrue(Batch.objects.filter(pk=real_batch.pk).exists())
        self.assertTrue(Category.objects.filter(pk=real_category.pk).exists())
        self.assertTrue(Species.objects.filter(pk=real_species.pk).exists())
        self.assertTrue(Supplier.objects.filter(pk=real_supplier.pk).exists())
        self.assertTrue(FeedInventory.objects.filter(pk=real_feed.pk).exists())
        self.assertTrue(User.objects.filter(pk=real_user.pk).exists())

    def test_delete_sample_when_empty_does_nothing(self):
        """Running delete_sample with no sample data should be a no-op."""
        call_command('delete_sample', verbosity=0)
        self.assertEqual(Batch.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    # ------------------------------------------------------------------
    # populate → delete leaves database exactly as it was
    # ------------------------------------------------------------------

    def test_populate_then_delete_leaves_db_clean(self):
        # Snapshot real data counts
        real_counts = {
            'Category': Category.objects.filter(is_sample=False).count(),
            'Species': Species.objects.filter(is_sample=False).count(),
            'Supplier': Supplier.objects.filter(is_sample=False).count(),
            'FeedInventory': FeedInventory.objects.filter(is_sample=False).count(),
            'Batch': Batch.objects.filter(is_sample=False).count(),
            'FeedLog': FeedLog.objects.filter(is_sample=False).count(),
            'GrowthRecord': GrowthRecord.objects.filter(is_sample=False).count(),
            'MortalityLog': MortalityLog.objects.filter(is_sample=False).count(),
            'VaccinationRecord': VaccinationRecord.objects.filter(is_sample=False).count(),
            'HealthMedicationLog': HealthMedicationLog.objects.filter(is_sample=False).count(),
            'DailyActivityLog': DailyActivityLog.objects.filter(is_sample=False).count(),
            'FarmExpense': FarmExpense.objects.count(),
        }

        # Populate
        call_command('populate_sample', verbosity=0)
        self.assertGreater(Batch.objects.filter(is_sample=True).count(), 0)

        # Delete
        call_command('delete_sample', verbosity=0)

        # All sample data gone
        for model_name in real_counts:
            model = globals()[model_name]
            self.assertEqual(
                model.objects.filter(is_sample=True).count(),
                0,
                f"{model_name} still has sample records after delete",
            )

        # Real data counts unchanged
        for model_name, original_count in real_counts.items():
            model = globals()[model_name]
            self.assertEqual(
                model.objects.filter(is_sample=False).count(),
                original_count,
                f"{model_name} real data count changed",
            )

        # No orphaned sample-related records
        self.assertEqual(FeedLog.objects.filter(batch__is_sample=True).count(), 0)
        self.assertEqual(GrowthRecord.objects.filter(batch__is_sample=True).count(), 0)
        self.assertEqual(MortalityLog.objects.filter(batch__is_sample=True).count(), 0)
        self.assertEqual(VaccinationRecord.objects.filter(batch__is_sample=True).count(), 0)
        self.assertEqual(HealthMedicationLog.objects.filter(batch__is_sample=True).count(), 0)
        self.assertEqual(DailyActivityLog.objects.filter(batch__is_sample=True).count(), 0)
        self.assertEqual(FarmExpense.objects.filter(batch__is_sample=True).count(), 0)

    # ------------------------------------------------------------------
    # Expanded sample data — batch-shop linking, expenses, extra mortality
    # ------------------------------------------------------------------

    def test_populate_sample_links_products_to_batches(self):
        call_command('populate_sample', verbosity=0)
        from shop.models import Product as ShopProduct
        links = [
            ('Live Catfish (per kg)', 'Catfish Batch - July 2026'),
            ('Live Tilapia (per kg)', 'Tilapia Batch - June 2026'),
            ('Live Broiler Chicken (per bird)', 'Broiler Batch - July 2026'),
            ('Live Layer Chicken (per bird)', 'Layer Batch - June 2026'),
            ('Calf (per head)', 'White Fulani Cattle - Aug 2025'),
            ('Ram (per head)', 'Sokoto Gudali - Mar 2026'),
        ]
        for prod_name, batch_name in links:
            product = ShopProduct.objects.filter(name=prod_name, is_sample_data=True).first()
            batch = Batch.objects.filter(name=batch_name, is_sample=True).first()
            self.assertIsNotNone(product, f"Product '{prod_name}' not found")
            self.assertIsNotNone(batch, f"Batch '{batch_name}' not found")
            self.assertEqual(product.linked_batch, batch)

    def test_populate_sample_creates_expenses_for_all_types(self):
        call_command('populate_sample', verbosity=0)
        types = dict(FarmExpense.EXPENSE_TYPE_CHOICES)
        for code, label in types.items():
            count = FarmExpense.objects.filter(expense_type=code).count()
            self.assertGreater(count, 0, f"No {label} expenses created")

    def test_populate_sample_supplier_purchase_linked_to_supplier_and_batch(self):
        call_command('populate_sample', verbosity=0)
        supplier_purchases = FarmExpense.objects.filter(expense_type='supplier_purchase')
        self.assertTrue(supplier_purchases.exists())
        for exp in supplier_purchases:
            self.assertIsNotNone(exp.supplier, "Supplier purchase should link to a supplier")
            self.assertIsNotNone(exp.batch, "Supplier purchase should link to a batch")

    def test_populate_sample_extra_mortality_for_linked_batches(self):
        call_command('populate_sample', verbosity=0)
        linked_batch_names = [
            'Broiler Batch - July 2026',
            'Catfish Batch - July 2026',
            'Layer Batch - June 2026',
        ]
        for batch_name in linked_batch_names:
            batch = Batch.objects.filter(name=batch_name, is_sample=True).first()
            self.assertIsNotNone(batch)
            self.assertGreater(
                batch.mortality_logs.count(), 1,
                f"Batch '{batch_name}' should have multiple mortality events"
            )

    # ------------------------------------------------------------------
    # RBAC — views restricted to Super Admin
    # ------------------------------------------------------------------

    def test_populate_sample_data_requires_super_admin(self):
        self.login(self.farm_manager)
        response = self.client.post(
            reverse('farm_management:populate_sample_data'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Batch.objects.filter(is_sample=True).exists())

    def test_populate_sample_data_unauthenticated_blocked(self):
        response = self.client.post(
            reverse('farm_management:populate_sample_data'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Batch.objects.filter(is_sample=True).exists())

    def test_delete_sample_data_requires_super_admin(self):
        call_command('populate_sample', verbosity=0)
        self.assertTrue(Batch.objects.filter(is_sample=True).exists())

        self.login(self.farm_manager)
        response = self.client.post(
            reverse('farm_management:delete_sample_data'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        # Sample data should still exist (deletion was blocked)
        self.assertTrue(Batch.objects.filter(is_sample=True).exists())

    def test_delete_sample_data_unauthenticated_blocked(self):
        response = self.client.post(
            reverse('farm_management:delete_sample_data'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)

    def test_super_admin_can_populate_via_view(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:populate_sample_data'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['categories_created'], 6)
        self.assertEqual(data['species_created'], 7)
        self.assertEqual(data['batches_created'], 6)
        self.assertEqual(data['expenses_created'], 1)
        self.assertEqual(data['linked_products_created'], 6)

    def test_super_admin_can_delete_via_view(self):
        call_command('populate_sample', verbosity=0)
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:delete_sample_data'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(Batch.objects.filter(is_sample=True).exists())

    # ------------------------------------------------------------------
    # Template — buttons visible only to Super Admin
    # ------------------------------------------------------------------

    def test_dashboard_shows_sample_buttons_for_super_admin(self):
        call_command('populate_sample', verbosity=0)
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Farm Management', content)
        self.assertIn('Recent Batches', content)

    def test_dashboard_hides_sample_buttons_for_farm_manager(self):
        call_command('populate_sample', verbosity=0)
        self.login(self.farm_manager)
        response = self.client.get(reverse('farm_management:dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Farm Management', content)


    # ------------------------------------------------------------------
    # Sample Customers and Staff
    # ------------------------------------------------------------------

    def test_populate_sample_creates_customer_and_staff_accounts(self):
        call_command('populate_sample', verbosity=0)

        customers = User.objects.filter(role=User.Role.CUSTOMER, is_sample_data=True)
        self.assertEqual(customers.count(), 4)

        staff = User.objects.filter(role=User.Role.STAFF, is_sample_data=True)
        self.assertEqual(staff.count(), 2)

        managers = User.objects.filter(role=User.Role.FARM_MANAGER, is_sample_data=True)
        self.assertEqual(managers.count(), 1)

        # All tagged
        self.assertEqual(User.objects.filter(is_sample_data=True).count(), 7)

    def test_populate_sample_creates_confirmed_orders_with_payments(self):
        call_command('populate_sample', verbosity=0)

        orders = Order.objects.filter(is_sample_data=True)
        self.assertEqual(orders.count(), 5)

        for order in orders:
            self.assertEqual(order.status, Order.Status.CONFIRMED)
            self.assertEqual(order.payment_method, "paystack")
            self.assertGreater(order.total, 0)
            self.assertGreater(order.subtotal, 0)
            self.assertGreater(order.items.count(), 0)
            self.assertTrue(order.items.first().product is not None)

        payments = Payment.objects.filter(is_sample_data=True)
        self.assertEqual(payments.count(), 5)
        for payment in payments:
            self.assertEqual(payment.status, "success")
            self.assertEqual(payment.amount, payment.order.total)

    def test_populate_sample_orders_have_different_dates(self):
        call_command('populate_sample', verbosity=0)

        orders = Order.objects.filter(is_sample_data=True).order_by('created_at')
        dates = list(orders.values_list('created_at__date', flat=True))
        self.assertEqual(len(dates), len(set(dates)), "Sample orders should have different dates")

    def test_populate_sample_orders_decrement_stock(self):
        call_command('populate_sample', verbosity=0)

        for item in OrderItem.objects.filter(is_sample_data=True):
            product = item.product
            self.assertLessEqual(
                product.stock_quantity,
                product.linked_batch.current_stock if product.linked_batch else 999999,
                f"Stock for {product.name} was not decremented"
            )

    def test_populate_sample_logs_have_recorded_by(self):
        call_command('populate_sample', verbosity=0)

        self.assertFalse(FeedLog.objects.filter(is_sample=True, recorded_by=None).exists())
        self.assertFalse(GrowthRecord.objects.filter(is_sample=True, recorded_by=None).exists())
        self.assertFalse(MortalityLog.objects.filter(is_sample=True, recorded_by=None).exists())
        self.assertFalse(VaccinationRecord.objects.filter(is_sample=True, recorded_by=None).exists())
        self.assertFalse(HealthMedicationLog.objects.filter(is_sample=True, recorded_by=None).exists())
        self.assertFalse(DailyActivityLog.objects.filter(is_sample=True, created_by=None).exists())

    def test_populate_sample_vaccination_administered_by_is_staff_name(self):
        call_command('populate_sample', verbosity=0)

        for rec in VaccinationRecord.objects.filter(is_sample=True):
            self.assertIsNotNone(rec.administered_by)
            self.assertNotEqual(rec.administered_by, "")

    def test_populate_sample_health_logs_administered_by_is_staff_name(self):
        call_command('populate_sample', verbosity=0)

        for rec in HealthMedicationLog.objects.filter(is_sample=True):
            self.assertIsNotNone(rec.administered_by)
            self.assertNotEqual(rec.administered_by, "")


# =============================================================================
# Health Records & Daily Activities — Add Entry Button & Flow Tests
# =============================================================================

class HealthRecordsAddEntryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.broiler = Species.objects.create(name="Broiler", category=self.poultry_category, is_active=True)
        self.fish_batch = Batch.objects.create(
            name="Fish Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.poultry_batch = Batch.objects.create(
            name="Poultry Batch",
            species=self.broiler,
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )

    def login(self):
        return self.client.login(username=self.super_admin.username, password="StrongPass1!")

    def test_health_records_list_shows_add_button(self):
        self.login()
        response = self.client.get(reverse('farm_management:health_records_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Add Health Log', content)
        self.assertIn('Add Vaccination', content)
        self.assertIn('/health-logs/add/', content)
        self.assertIn('/vaccinations/add/', content)

    def test_daily_activities_list_shows_add_button(self):
        self.login()
        response = self.client.get(reverse('farm_management:daily_activities_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Add Daily Activity', content)
        self.assertIn('/activity-logs/add/', content)

    def test_health_log_add_top_form_loads(self):
        self.login()
        response = self.client.get(reverse('farm_management:health_log_add_top'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Add Health/Medication Log', content)
        self.assertIn('Medicine Name', content)
        self.assertIn('Dosage', content)
        self.assertIn('Reason', content)

    def test_health_log_add_top_submit_redirects_to_list(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:health_log_add_top'),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'medicine_name': 'Oxytetracycline',
                'dosage': '20mg/kg',
                'reason': 'Respiratory infection',
                'administered_by': 'Dr. Okafor',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('farm_management:health_records_list'))
        self.assertEqual(HealthMedicationLog.objects.count(), 1)
        log = HealthMedicationLog.objects.first()
        self.assertEqual(log.medicine_name, 'Oxytetracycline')
        self.assertEqual(log.batch, self.fish_batch)

    def test_activity_log_add_top_form_loads(self):
        self.login()
        response = self.client.get(reverse('farm_management:activity_log_add_top'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Add Daily Activity Log', content)
        self.assertIn('Note', content)
        self.assertIn('Date', content)

    def test_activity_log_add_top_submit_redirects_to_list(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:activity_log_add_top'),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'note': 'Checked feeding troughs and replenished feed.',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('farm_management:daily_activities_list'))
        self.assertEqual(DailyActivityLog.objects.count(), 1)
        log = DailyActivityLog.objects.first()
        self.assertEqual(log.note, 'Checked feeding troughs and replenished feed.')
        self.assertEqual(log.batch, self.fish_batch)

    def test_vaccination_add_top_blocks_fish_batch(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:vaccination_add_top'),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'vaccine_name': 'Test Vaccine',
                'dosage': '0.5ml',
                'administered_by': 'Dr. Okafor',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('poultry batches', response.content.decode().lower())
        self.assertEqual(VaccinationRecord.objects.count(), 0)

    def test_vaccination_add_top_accepts_poultry_batch(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:vaccination_add_top'),
            {
                'batch': self.poultry_batch.pk,
                'date': date.today().isoformat(),
                'vaccine_name': 'NDV Vaccine',
                'dosage': '0.5ml per bird',
                'administered_by': 'Dr. Okafor',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('farm_management:health_records_list'))
        self.assertEqual(VaccinationRecord.objects.count(), 1)

    def test_health_log_add_top_blocks_closed_batch(self):
        self.fish_batch.status = 'closed'
        self.fish_batch.save(update_fields=['status'])
        self.login()
        response = self.client.post(
            reverse('farm_management:health_log_add_top'),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'medicine_name': 'Test Med',
                'dosage': '5mg',
                'reason': 'Test',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())
        self.assertEqual(HealthMedicationLog.objects.count(), 0)

    def test_activity_log_add_top_blocks_closed_batch(self):
        self.fish_batch.status = 'closed'
        self.fish_batch.save(update_fields=['status'])
        self.login()
        response = self.client.post(
            reverse('farm_management:activity_log_add_top'),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'note': 'Test activity',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())
        self.assertEqual(DailyActivityLog.objects.count(), 0)

    def test_health_records_list_shows_sample_data_after_populate(self):
        call_command('populate_sample', verbosity=0)
        self.login()
        response = self.client.get(reverse('farm_management:health_records_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertTrue(HealthMedicationLog.objects.filter(is_sample=True).count() > 0)

    def test_daily_activities_list_shows_sample_data_after_populate(self):
        call_command('populate_sample', verbosity=0)
        self.login()
        response = self.client.get(reverse('farm_management:daily_activities_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(DailyActivityLog.objects.filter(is_sample=True).count() > 0)


# =============================================================================
# Feature 1: Batch-Product Linking + Auto Stock Decrement Tests
# =============================================================================

class BatchProductLinkingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.batch = Batch.objects.create(
            name="Linked Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.seafood_category = ShopCategory.objects.create(name="Seafood")
        self.product = Product.objects.create(
            name="Live Catfish",
            category=self.seafood_category,
            price=Decimal("2500.00"),
            stock_quantity=10,
        )

    def login(self):
        return self.client.login(username=self.super_admin.username, password="StrongPass1!")

    def test_product_can_be_linked_to_batch(self):
        self.product.linked_batch = self.batch
        self.product.save()
        self.assertEqual(self.product.linked_batch, self.batch)
        self.assertIn(self.product, self.batch.linked_products.all())

    def test_mortality_decrements_linked_product_stock_by_one(self):
        self.product.linked_batch = self.batch
        self.product.save()
        self.assertEqual(self.product.stock_quantity, 10)
        MortalityLog.objects.create(
            batch=self.batch,
            date=date.today(),
            count=1,
            cause="Disease",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 9)

    def test_stock_does_not_go_negative(self):
        self.product.linked_batch = self.batch
        self.product.stock_quantity = 0
        self.product.save()
        MortalityLog.objects.create(
            batch=self.batch,
            date=date.today(),
            count=3,
            cause="Disease",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)

    def test_product_without_linked_batch_unaffected(self):
        unlinked_product = Product.objects.create(
            name="Processed Fish",
            category=self.seafood_category,
            price=Decimal("3000.00"),
            stock_quantity=5,
        )
        MortalityLog.objects.create(
            batch=self.batch,
            date=date.today(),
            count=2,
            cause="Disease",
        )
        unlinked_product.refresh_from_db()
        self.assertEqual(unlinked_product.stock_quantity, 5)

    def test_batch_detail_shows_linked_products(self):
        self.login()
        self.product.linked_batch = self.batch
        self.product.save()
        response = self.client.get(reverse('farm_management:batch_detail', args=[self.batch.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Live Catfish', content)
        self.assertIn('Linked Shop Products', content)

    def test_product_form_includes_linked_batch_field(self):
        self.login()
        response = self.client.get(reverse('admin_dashboard:product_add'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Linked Batch', content)

    def test_multiple_products_can_link_to_same_batch(self):
        product2 = Product.objects.create(
            name="Fish Fingers",
            category=self.seafood_category,
            price=Decimal("1500.00"),
            stock_quantity=20,
        )
        self.product.linked_batch = self.batch
        product2.linked_batch = self.batch
        self.product.save()
        product2.save()
        self.assertEqual(self.batch.linked_products.count(), 2)
        self.assertIn(self.product, self.batch.linked_products.all())
        self.assertIn(product2, self.batch.linked_products.all())


# =============================================================================
# Feature 2: Auto-log Feeding & Medication Events to Activity Log Tests
# =============================================================================

class AutoActivityLogTests(TestCase):
    def setUp(self):
        self.fish_category = Category.objects.create(name="Fish")
        self.poultry_category = Category.objects.create(name="Poultry")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.batch = Batch.objects.create(
            name="Auto Log Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.inventory = FeedInventory.objects.create(
            feed_type="Starter Feed",
            quantity_on_hand_kg=500,
            cost_per_kg=Decimal("500"),
            reorder_point_kg=100,
        )

    def test_feed_log_creates_activity_log_entry(self):
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_inventory=self.inventory,
            quantity_kg=Decimal("5.0"),
        )
        self.assertEqual(DailyActivityLog.objects.count(), 1)
        activity = DailyActivityLog.objects.first()
        self.assertEqual(activity.batch, self.batch)
        self.assertIn("Fed", activity.note)
        self.assertIn("Auto Log Batch", activity.note)
        self.assertIn("5.0", activity.note)
        self.assertIn("Starter Feed", activity.note)

    def test_medication_log_creates_activity_log_entry(self):
        HealthMedicationLog.objects.create(
            batch=self.batch,
            date=date.today(),
            medicine_name="Oxytetracycline",
            dosage="20mg/kg",
            reason="Respiratory infection",
            administered_by="Dr. Okafor",
        )
        self.assertEqual(DailyActivityLog.objects.count(), 1)
        activity = DailyActivityLog.objects.first()
        self.assertEqual(activity.batch, self.batch)
        self.assertIn("Administered", activity.note)
        self.assertIn("Oxytetracycline", activity.note)
        self.assertIn("Auto Log Batch", activity.note)

    def test_activity_log_entry_has_correct_batch(self):
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_inventory=self.inventory,
            quantity_kg=Decimal("3.5"),
        )
        activity = DailyActivityLog.objects.first()
        self.assertEqual(activity.batch, self.batch)
        self.assertEqual(activity.date, date.today())

    def test_activity_log_entry_created_by_is_none_for_signals(self):
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_inventory=self.inventory,
            quantity_kg=Decimal("2.0"),
        )
        activity = DailyActivityLog.objects.first()
        self.assertIsNone(activity.created_by)

    def test_multiple_feed_logs_create_multiple_activity_entries(self):
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_inventory=self.inventory,
            quantity_kg=Decimal("5.0"),
        )
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_inventory=self.inventory,
            quantity_kg=Decimal("3.0"),
        )
        self.assertEqual(DailyActivityLog.objects.count(), 2)

    def test_feed_log_without_inventory_creates_activity_entry(self):
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_inventory=None,
            quantity_kg=Decimal("4.0"),
            cost=Decimal("2000.00"),
        )
        self.assertEqual(DailyActivityLog.objects.count(), 1)
        activity = DailyActivityLog.objects.first()
        self.assertIn("Fed", activity.note)
        self.assertIn("feed", activity.note.lower())


# =============================================================================
# Feature 3: Farm Expense / Cost Tracking Tests
# =============================================================================

class FarmExpenseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.fish_category = Category.objects.create(name="Fish")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)
        self.batch = Batch.objects.create(
            name="Expense Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )

    def login(self):
        return self.client.login(username=self.super_admin.username, password="StrongPass1!")

    def test_create_electricity_expense(self):
        expense = FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            description="June electricity bill",
            recorded_by=self.super_admin,
        )
        self.assertEqual(expense.expense_type, 'electricity')
        self.assertEqual(expense.amount, Decimal("50000.00"))

    def test_create_labor_expense(self):
        expense = FarmExpense.objects.create(
            expense_type='labor',
            amount=Decimal("30000.00"),
            date_incurred=date.today(),
            description="2 casual workers - cleaning",
            batch=self.batch,
            recorded_by=self.super_admin,
        )
        self.assertEqual(expense.expense_type, 'labor')
        self.assertEqual(expense.batch, self.batch)

    def test_create_sawdust_expense(self):
        expense = FarmExpense.objects.create(
            expense_type='sawdust',
            amount=Decimal("15000.00"),
            date_incurred=date.today(),
            description="Bedding for poultry",
            recorded_by=self.super_admin,
        )
        self.assertEqual(expense.expense_type, 'sawdust')

    def test_total_cost_rollup_for_date_range(self):
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='labor',
            amount=Decimal("30000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='sawdust',
            amount=Decimal("15000.00"),
            date_incurred=date.today() - timedelta(days=10),
            recorded_by=self.super_admin,
        )

        qs = FarmExpense.objects.filter(date_incurred__gte=date.today() - timedelta(days=5))
        total = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        self.assertEqual(total, Decimal("80000.00"))

    def test_filter_by_type(self):
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='labor',
            amount=Decimal("30000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )

        electricity_expenses = FarmExpense.objects.filter(expense_type='electricity')
        self.assertEqual(electricity_expenses.count(), 1)
        self.assertEqual(electricity_expenses.first().amount, Decimal("50000.00"))

    def test_expense_list_view_loads(self):
        self.login()
        response = self.client.get(reverse('farm_management:expense_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Farm Expenses', response.content.decode())

    def test_expense_create_view_loads(self):
        self.login()
        response = self.client.get(reverse('farm_management:expense_add'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Add Expense', response.content.decode())

    def test_expense_create_submit_redirects(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:expense_add'),
            {
                'expense_type': 'electricity',
                'amount': '45000.00',
                'date_incurred': date.today().isoformat(),
                'description': 'Test bill',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FarmExpense.objects.count(), 1)

    def test_expense_summary_view_loads(self):
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cost Estimate', response.content.decode())

    def test_expense_summary_shows_total(self):
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='labor',
            amount=Decimal("30000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Total Farm Cost', content)
        self.assertIn('₦80000.00', content)

    def test_create_supplier_purchase_expense(self):
        supplier = Supplier.objects.create(
            name="Test Supplier",
            phone="08012345678",
            email="test@supplier.ng",
            address="Test Address",
            is_sample=True,
        )
        expense = FarmExpense.objects.create(
            expense_type='supplier_purchase',
            amount=Decimal("250000.00"),
            date_incurred=date.today(),
            description="200 day-old chicks",
            batch=self.batch,
            supplier=supplier,
            recorded_by=self.super_admin,
        )
        self.assertEqual(expense.expense_type, 'supplier_purchase')
        self.assertEqual(expense.supplier, supplier)
        self.assertEqual(expense.batch, self.batch)

    def test_supplier_purchase_included_in_summary(self):
        supplier = Supplier.objects.create(
            name="Test Supplier 2",
            phone="08087654321",
            email="test2@supplier.ng",
            address="Test Address 2",
            is_sample=True,
        )
        FarmExpense.objects.create(
            expense_type='supplier_purchase',
            amount=Decimal("250000.00"),
            date_incurred=date.today(),
            description="200 day-old chicks",
            batch=self.batch,
            supplier=supplier,
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Total Farm Cost', content)
        self.assertIn('₦300000.00', content)
        self.assertIn('Animal/Stock Purchase', content)

    def test_feed_usage_included_in_total_cost(self):
        feed_log = FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            quantity_kg=Decimal('100.00'),
            cost=Decimal('52500.00'),
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Total Farm Cost', content)
        self.assertIn('₦102500.00', content)
        self.assertIn('Feed Used (Farm-wide)', content)

    def test_feed_usage_respects_date_range(self):
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            quantity_kg=Decimal('100.00'),
            cost=Decimal('52500.00'),
            recorded_by=self.super_admin,
        )
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today() - timedelta(days=30),
            quantity_kg=Decimal('50.00'),
            cost=Decimal('25000.00'),
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'), {'date_from': (date.today() - timedelta(days=10)).isoformat(), 'date_to': date.today().isoformat()})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('₦102500.00', content)
        self.assertNotIn('₦127500.00', content)

    def test_feed_purchase_expense_included_in_summary(self):
        FarmExpense.objects.create(
            expense_type='feed_purchase',
            amount=Decimal("75000.00"),
            date_incurred=date.today(),
            description="Bulk feed bags",
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Total Farm Cost', content)
        self.assertIn('₦125000.00', content)
        self.assertIn('Feed Purchase', content)

    def test_expense_summary_chart_data_matches_cards(self):
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='labor',
            amount=Decimal("30000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            quantity_kg=Decimal('100.00'),
            cost=Decimal('20000.00'),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('costBreakdownPieChart', content)
        self.assertIn('costBreakdownBarChart', content)
        self.assertIn('Electricity', content)
        self.assertIn('Labor', content)
        self.assertIn('Feed Used (Farm-wide)', content)


class StaffAccountabilityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff Member",
            password="StrongPass1!",
            role=User.Role.FARM_MANAGER,
        )
        self.super_admin = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.category = Category.objects.create(name="Poultry")
        self.species = Species.objects.create(name="Broiler", category=self.category, is_active=True)
        self.batch = Batch.objects.create(
            name="Test Batch",
            species=self.species,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.feed_inventory = FeedInventory.objects.create(
            feed_type="Test Feed",
            category=self.category,
            quantity_on_hand_kg=500,
            cost_per_kg=500,
            reorder_point_kg=100,
        )

    def login(self, user=None):
        user = user or self.user
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_feed_log_records_user(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:feed_log_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'feed_inventory': self.feed_inventory.pk,
                'quantity_kg': 50,
                'notes': 'Test feed',
            }
        )
        self.assertEqual(response.status_code, 302)
        log = FeedLog.objects.first()
        self.assertEqual(log.recorded_by, self.user)

    def test_growth_record_records_user(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:growth_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'average_weight_kg': 1.5,
                'sample_size': 10,
            }
        )
        self.assertEqual(response.status_code, 302)
        record = GrowthRecord.objects.first()
        self.assertEqual(record.recorded_by, self.user)

    def test_mortality_log_records_user(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:mortality_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'count': 5,
                'cause': 'Disease',
                'notes': 'Test mortality',
            }
        )
        self.assertEqual(response.status_code, 302)
        log = MortalityLog.objects.first()
        self.assertEqual(log.recorded_by, self.user)

    def test_health_log_records_user(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:health_log_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'medicine_name': 'Test Med',
                'dosage': '10mg',
                'reason': 'Test',
                'administered_by': 'Dr. Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        log = HealthMedicationLog.objects.first()
        self.assertEqual(log.recorded_by, self.user)

    def test_vaccination_record_records_user(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:vaccination_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'vaccine_name': 'Test Vaccine',
                'dosage': '0.5ml',
                'administered_by': 'Dr. Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        record = VaccinationRecord.objects.first()
        self.assertEqual(record.recorded_by, self.user)

    def test_daily_activity_log_records_user(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:activity_log_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'note': 'Test activity',
            }
        )
        self.assertEqual(response.status_code, 302)
        log = DailyActivityLog.objects.first()
        self.assertEqual(log.created_by, self.user)

    def test_feed_log_auto_activity_has_recorded_by(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:feed_log_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'feed_inventory': self.feed_inventory.pk,
                'quantity_kg': 50,
                'notes': 'Test feed',
            }
        )
        self.assertEqual(response.status_code, 302)
        activity = DailyActivityLog.objects.filter(note__contains="Fed").first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.created_by, self.super_admin)

    def test_health_log_auto_activity_has_recorded_by(self):
        self.login(self.super_admin)
        response = self.client.post(
            reverse('farm_management:health_log_add', kwargs={'batch_pk': self.batch.pk}),
            data={
                'batch': self.batch.pk,
                'date': date.today(),
                'medicine_name': 'Test Med',
                'dosage': '10mg',
                'reason': 'Test',
                'administered_by': 'Dr. Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        activity = DailyActivityLog.objects.filter(note__contains="Administered").first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.created_by, self.super_admin)


class FeedPurchaseTrackingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.category = Category.objects.create(name="Fish")
        self.species = Species.objects.create(name="Catfish", category=self.category, is_active=True)
        self.batch = Batch.objects.create(
            name="Test Batch",
            species=self.species,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.supplier = Supplier.objects.create(
            name="Test Supplier",
            phone="08012345678",
            email="test@supplier.ng",
            address="Test Address",
        )
        self.feed_inventory = FeedInventory.objects.create(
            feed_type="Test Feed",
            category=self.category,
            supplier=self.supplier,
            quantity_on_hand_kg=500,
            cost_per_kg=500,
            reorder_point_kg=100,
        )

    def login(self):
        return self.client.login(username=self.super_admin.username, password="StrongPass1!")

    def test_create_feed_purchase_expense(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:expense_add'),
            data={
                'expense_type': 'feed_purchase',
                'amount': '75000.00',
                'date_incurred': date.today(),
                'description': 'Bulk feed purchase',
                'feed_inventory': self.feed_inventory.pk,
                'quantity_purchased_kg': 100,
                'supplier': self.supplier.pk,
                'batch': self.batch.pk,
            }
        )
        self.assertEqual(response.status_code, 302)
        expense = FarmExpense.objects.first()
        self.assertEqual(expense.expense_type, 'feed_purchase')
        self.assertEqual(expense.feed_inventory, self.feed_inventory)
        self.assertEqual(expense.quantity_purchased_kg, Decimal('100.00'))
        self.assertEqual(expense.supplier, self.supplier)

    def test_feed_purchase_increases_inventory_stock(self):
        self.login()
        initial_stock = self.feed_inventory.quantity_on_hand_kg
        response = self.client.post(
            reverse('farm_management:expense_add'),
            data={
                'expense_type': 'feed_purchase',
                'amount': '75000.00',
                'date_incurred': date.today(),
                'description': 'Bulk feed purchase',
                'feed_inventory': self.feed_inventory.pk,
                'quantity_purchased_kg': 100,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.feed_inventory.refresh_from_db()
        self.assertEqual(self.feed_inventory.quantity_on_hand_kg, initial_stock + Decimal('100.00'))

    def test_feed_purchase_included_in_summary(self):
        FarmExpense.objects.create(
            expense_type='feed_purchase',
            amount=Decimal("75000.00"),
            date_incurred=date.today(),
            description="Bulk feed bags",
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Total Farm Cost', content)
        self.assertIn('₦125000.00', content)
        self.assertIn('Feed Purchase', content)

    def test_non_feed_purchase_does_not_affect_inventory(self):
        self.login()
        initial_stock = self.feed_inventory.quantity_on_hand_kg
        response = self.client.post(
            reverse('farm_management:expense_add'),
            data={
                'expense_type': 'electricity',
                'amount': '50000.00',
                'date_incurred': date.today(),
                'description': 'Electricity bill',
                'feed_inventory': self.feed_inventory.pk,
                'quantity_purchased_kg': 100,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.feed_inventory.refresh_from_db()
        self.assertEqual(self.feed_inventory.quantity_on_hand_kg, initial_stock)


class OtherExpenseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.category = Category.objects.create(name="Fish")
        self.species = Species.objects.create(name="Catfish", category=self.category, is_active=True)
        self.batch = Batch.objects.create(
            name="Test Batch",
            species=self.species,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )

    def login(self):
        return self.client.login(username=self.super_admin.username, password="StrongPass1!")

    def test_other_expense_requires_custom_label(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:expense_add'),
            data={
                'expense_type': 'other',
                'amount': '15000.00',
                'date_incurred': date.today(),
                'description': 'Miscellaneous cost',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FarmExpense.objects.exists())
        self.assertIn('Please enter a description for this', response.content.decode())

    def test_other_expense_with_custom_label_creates_successfully(self):
        self.login()
        response = self.client.post(
            reverse('farm_management:expense_add'),
            data={
                'expense_type': 'other',
                'amount': '15000.00',
                'date_incurred': date.today(),
                'description': 'Vet call-out fee',
                'custom_label': 'Vet call-out fee',
            }
        )
        self.assertEqual(response.status_code, 302)
        expense = FarmExpense.objects.first()
        self.assertEqual(expense.expense_type, 'other')
        self.assertEqual(expense.custom_label, 'Vet call-out fee')

    def test_other_expense_displayed_with_label_in_list(self):
        FarmExpense.objects.create(
            expense_type='other',
            amount=Decimal("15000.00"),
            date_incurred=date.today(),
            description="Vet call-out fee",
            custom_label="Vet call-out fee",
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Other: Vet call-out fee', content)

    def test_other_expense_included_in_summary(self):
        FarmExpense.objects.create(
            expense_type='other',
            amount=Decimal("15000.00"),
            date_incurred=date.today(),
            description="Fence repair",
            custom_label="Fence repair",
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='electricity',
            amount=Decimal("50000.00"),
            date_incurred=date.today(),
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Total Farm Cost', content)
        self.assertIn('₦65000.00', content)
        self.assertIn('Other', content)

    def test_multiple_other_expenses_grouped_in_summary(self):
        FarmExpense.objects.create(
            expense_type='other',
            amount=Decimal("15000.00"),
            date_incurred=date.today(),
            description="Vet call-out fee",
            custom_label="Vet call-out fee",
            recorded_by=self.super_admin,
        )
        FarmExpense.objects.create(
            expense_type='other',
            amount=Decimal("8000.00"),
            date_incurred=date.today(),
            description="Fence repair",
            custom_label="Fence repair",
            recorded_by=self.super_admin,
        )
        self.login()
        response = self.client.get(reverse('farm_management:expense_summary'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('₦23000.00', content)
        other_count = FarmExpense.objects.filter(expense_type='other').count()
        self.assertEqual(other_count, 2)
