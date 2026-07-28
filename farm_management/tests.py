from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.management import call_command
from decimal import Decimal
from datetime import date, timedelta

from notifications.models import Notification
from .models import Batch, FeedLog, GrowthRecord, MortalityLog, HarvestRecord, FeedInventory, Supplier, HealthMedicationLog, VaccinationRecord, WaterQualityLog, DailyActivityLog

User = get_user_model()


class BatchModelTests(TestCase):
    def test_batch_creation_sets_current_stock(self):
        batch = Batch.objects.create(
            name="Catfish Batch 1",
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.assertEqual(batch.current_stock, 100)

    def test_batch_str(self):
        batch = Batch.objects.create(
            name="Test Batch",
            species="tilapia",
            initial_count=50,
            start_date=date.today(),
            season="dry",
        )
        self.assertEqual(str(batch), "Test Batch")

    def test_is_fish_property(self):
        fish_batch = Batch.objects.create(
            name="Fish",
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.assertTrue(fish_batch.is_fish)
        self.assertFalse(fish_batch.is_poultry)

    def test_is_poultry_property(self):
        poultry_batch = Batch.objects.create(
            name="Broilers",
            species="broiler",
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )
        self.assertTrue(poultry_batch.is_poultry)
        self.assertFalse(poultry_batch.is_fish)

    def test_mortality_rate_calculation(self):
        batch = Batch.objects.create(
            name="Mortality Test",
            species="catfish",
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
            species="catfish",
            initial_count=0,
            current_stock=0,
            start_date=date.today(),
            season="rainy",
        )
        self.assertEqual(batch.mortality_rate, 0)

    def test_feed_conversion_ratio(self):
        batch = Batch.objects.create(
            name="FCR Test",
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Test Feed",
            quantity_kg=Decimal("100.0"),
            cost=Decimal("50000"),
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
            species="catfish",
            initial_count=100,
            current_stock=80,
            start_date=date.today(),
            season="rainy",
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Test Feed",
            quantity_kg=Decimal("100.0"),
            cost=Decimal("50000"),
        )
        self.assertIsNone(batch.feed_conversion_ratio)

    def test_total_feed_cost(self):
        batch = Batch.objects.create(
            name="Cost Test",
            species="catfish",
            initial_count=100,
            current_stock=80,
            start_date=date.today(),
            season="rainy",
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Feed A",
            quantity_kg=Decimal("50.0"),
            cost=Decimal("25000"),
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Feed B",
            quantity_kg=Decimal("30.0"),
            cost=Decimal("18000"),
        )
        self.assertEqual(batch.total_feed_cost, Decimal("43000"))


class MortalityLogTests(TestCase):
    def test_mortality_decrements_stock(self):
        batch = Batch.objects.create(
            name="Stock Test",
            species="catfish",
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
            species="catfish",
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
            species="catfish",
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
            species="catfish",
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
    def test_feed_log_creation(self):
        batch = Batch.objects.create(
            name="Feed Test",
            species="catfish",
            initial_count=100,
            current_stock=80,
            start_date=date.today(),
            season="rainy",
        )
        log = FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Coppens",
            quantity_kg=Decimal("25.5"),
            cost=Decimal("12750"),
            notes="Morning feed",
        )
        self.assertEqual(log.feed_type, "Coppens")
        self.assertEqual(log.quantity_kg, Decimal("25.5"))


class GrowthRecordModelTests(TestCase):
    def test_growth_record_creation(self):
        batch = Batch.objects.create(
            name="Growth Test",
            species="catfish",
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )

    def login(self, user):
        return self.client.login(email=user.email, password="StrongPass1!")

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
                'species': 'tilapia',
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
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.batch.pk]),
            {
                'batch': self.batch.pk,
                'date': date.today().isoformat(),
                'feed_type': 'Test Feed',
                'quantity_kg': 50,
                'cost': 25000,
                'notes': 'Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FeedLog.objects.count(), 1)

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
        self.client.login(email=staff.email, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:batch_list'))
        self.assertEqual(response.status_code, 302)


class HarvestRecordTests(TestCase):
    def setUp(self):
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.batch.current_stock = 80
        self.batch.save(update_fields=['current_stock'])
        FeedLog.objects.create(
            batch=self.batch,
            date=date.today(),
            feed_type="Test Feed",
            quantity_kg=Decimal("100.0"),
            cost=Decimal("50000"),
        )

    def test_harvest_creates_and_closes_batch(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.closed_batch.status = 'closed'
        self.closed_batch.save(update_fields=['status'])

    def test_feed_log_blocked_on_closed_batch(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:feed_log_add', args=[self.closed_batch.pk]),
            {
                'batch': self.closed_batch.pk,
                'date': date.today().isoformat(),
                'feed_type': 'Test Feed',
                'quantity_kg': 10,
                'cost': 5000,
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('closed batch', response.content.decode().lower())
        self.assertEqual(FeedLog.objects.count(), 0)

    def test_growth_record_blocked_on_closed_batch(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def test_feed_inventory_list_loads(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:feed_inventory_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Feed Inventory', response.content.decode())

    def test_feed_inventory_create(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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


class Phase3LogTests(TestCase):
    def setUp(self):
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.poultry_batch = Batch.objects.create(
            name="Poultry Batch",
            species="broiler",
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )

    def test_health_log_create(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:health_log_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'medicine_name': 'Oxytetracycline',
                'dosage': '10mg/kg',
                'reason': 'Bacterial infection',
                'administered_by': 'Dr. Test',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HealthMedicationLog.objects.count(), 1)

    def test_health_log_blocked_on_closed_batch(self):
        self.fish_batch.status = 'closed'
        self.fish_batch.save(update_fields=['status'])
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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

    def test_water_quality_create_for_fish_batch(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:water_quality_add', args=[self.fish_batch.pk]),
            {
                'batch': self.fish_batch.pk,
                'date': date.today().isoformat(),
                'ph_level': 7.0,
                'temperature_c': 28.5,
                'oxygen_level': 5.5,
                'notes': 'Normal parameters',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WaterQualityLog.objects.count(), 1)

    def test_water_quality_blocked_for_poultry_batch(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
        response = self.client.post(
            reverse('farm_management:water_quality_add', args=[self.poultry_batch.pk]),
            {
                'batch': self.poultry_batch.pk,
                'date': date.today().isoformat(),
                'ph_level': 7.0,
                'temperature_c': 28.5,
                'oxygen_level': 5.5,
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('fish batches', response.content.decode().lower())
        self.assertEqual(WaterQualityLog.objects.count(), 0)

    def test_daily_activity_log_create(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        self.poultry_batch = Batch.objects.create(
            name="Poultry Batch",
            species="broiler",
            initial_count=200,
            start_date=date.today(),
            season="dry",
        )

    def test_vaccination_blocked_on_fish_batch(self):
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
        self.client.login(email=self.super_admin.email, password="StrongPass1!")
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
            species="catfish",
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Test Feed",
            quantity_kg=Decimal("10.0"),
            cost=Decimal("5000"),
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
            species="catfish",
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
            species="catfish",
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
        return self.client.login(email=user.email, password="StrongPass1!")

    def test_analytics_loads_for_super_admin(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('farm_management:analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Batch Analytics', response.content.decode())

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
        self.client.login(email=staff.email, password="StrongPass1!")
        response = self.client.get(reverse('farm_management:analytics'), follow=False)
        self.assertEqual(response.status_code, 302)

    def test_analytics_highlights_highest_feed(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Low Feed Batch",
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="High Feed Batch",
            species="tilapia",
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        FeedLog.objects.create(batch=batch1, date=date.today(), feed_type="A", quantity_kg=10, cost=1000)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_type="B", quantity_kg=50, cost=5000)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_type="B", quantity_kg=30, cost=3000)

        response = self.client.get(reverse('farm_management:analytics'))
        content = response.content.decode()
        self.assertIn('High Feed Batch', content)

    def test_analytics_highlights_best_fcr(self):
        self.login(self.super_admin)
        batch1 = Batch.objects.create(
            name="Bad FCR Batch",
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="Good FCR Batch",
            species="tilapia",
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        FeedLog.objects.create(batch=batch1, date=date.today(), feed_type="A", quantity_kg=200, cost=10000)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_type="B", quantity_kg=50, cost=5000)
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="High Mortality Batch",
            species="tilapia",
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
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        batch2 = Batch.objects.create(
            name="High Profit Batch",
            species="tilapia",
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        FeedLog.objects.create(batch=batch1, date=date.today(), feed_type="A", quantity_kg=100, cost=50000)
        FeedLog.objects.create(batch=batch2, date=date.today(), feed_type="B", quantity_kg=100, cost=50000)
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
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def login(self, user):
        return self.client.login(email=user.email, password="StrongPass1!")

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
        self.client.login(email=staff.email, password="StrongPass1!")
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
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def login(self, user):
        return self.client.login(email=user.email, password="StrongPass1!")

    def test_pdf_report_active_batch(self):
        self.login(self.super_admin)
        batch = Batch.objects.create(
            name="Active Batch Report",
            species="catfish",
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Test Feed",
            quantity_kg=50,
            cost=5000,
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
        self.assertIn('Active Batch Report', response.content.decode())
        self.assertIn('Feed Logs', response.content.decode())
        self.assertIn('Growth Records', response.content.decode())
        self.assertIn('Mortality Logs', response.content.decode())

    def test_pdf_report_closed_batch_with_harvest(self):
        self.login(self.super_admin)
        batch = Batch.objects.create(
            name="Closed Batch Report",
            species="tilapia",
            initial_count=100,
            start_date=date.today(),
            season="dry",
        )
        FeedLog.objects.create(
            batch=batch,
            date=date.today(),
            feed_type="Test Feed",
            quantity_kg=50,
            cost=5000,
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
        self.assertIn('Closed Batch Report', response.content.decode())
        self.assertIn('Harvest Record', response.content.decode())
        self.assertIn('Profit', response.content.decode())

    def test_pdf_report_staff_blocked(self):
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff",
            password="StrongPass1!",
            role=User.Role.STAFF,
        )
        self.client.login(email=staff.email, password="StrongPass1!")
        batch = Batch.objects.create(
            name="Staff Batch",
            species="catfish",
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
            species="catfish",
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
