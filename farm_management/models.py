from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

STATUS_CHOICES = [
    ('active', 'Active'),
    ('closed', 'Closed'),
]

SEASON_CHOICES = [
    ('rainy', 'Rainy Season'),
    ('dry', 'Dry Season'),
]


class Category(models.Model):
    """Category for species (e.g. Fish, Poultry)"""
    name = models.CharField(_("name"), max_length=100, unique=True)
    is_active = models.BooleanField(_("is active"), default=True)
    is_sample = models.BooleanField(_("sample data"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ['name']

    def __str__(self):
        return self.name


class Species(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name=_("category"), related_name='species')
    is_active = models.BooleanField(_("is active"), default=True)
    is_sample = models.BooleanField(_("sample data"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("species")
        verbose_name_plural = _("species")
        ordering = ['category__name', 'name']

    def __str__(self):
        return self.name


class Batch(models.Model):
    STATUS_CHOICES = STATUS_CHOICES
    SEASON_CHOICES = SEASON_CHOICES

    name = models.CharField(_("name"), max_length=100)
    species = models.ForeignKey(Species, on_delete=models.PROTECT, verbose_name=_("species"), related_name='batches')
    initial_count = models.PositiveIntegerField(_("initial count"))
    current_stock = models.PositiveIntegerField(_("current stock"))
    start_date = models.DateField(_("start date"))
    season = models.CharField(_("season"), max_length=10, choices=SEASON_CHOICES)
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("batch")
        verbose_name_plural = _("batches")
        ordering = ['-start_date']

    def save(self, *args, **kwargs):
        if not self.pk:
            self.current_stock = self.initial_count
        super().save(*args, **kwargs)

    @property
    def is_fish(self):
        return self.species.category.name.lower() == 'fish'

    @property
    def is_poultry(self):
        return self.species.category.name.lower() == 'poultry'

    @property
    def mortality_rate(self):
        deaths = self.initial_count - self.current_stock
        return round((deaths / self.initial_count) * 100, 2) if self.initial_count else 0

    @property
    def total_feed_cost(self):
        return self.feed_logs.aggregate(total=models.Sum('cost'))['total'] or 0

    @property
    def feed_conversion_ratio(self):
        total_feed = self.feed_logs.aggregate(total=models.Sum('quantity_kg'))['total'] or 0
        latest_growth = self.growth_records.order_by('-date').first()
        earliest_growth = self.growth_records.order_by('date').first()
        if not latest_growth or not earliest_growth or latest_growth == earliest_growth:
            return None
        weight_gain = (latest_growth.average_weight_kg - earliest_growth.average_weight_kg) * self.current_stock
        return round(total_feed / weight_gain, 2) if weight_gain > 0 else None

    def __str__(self):
        return f"{self.name} ({self.species.category.name} — {self.species.name})"


class FeedLog(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='feed_logs', verbose_name=_("batch"))
    date = models.DateField(_("date"))
    feed_inventory = models.ForeignKey('FeedInventory', on_delete=models.SET_NULL, verbose_name=_("feed inventory"), null=True, blank=True, related_name='feed_logs')
    quantity_kg = models.DecimalField(_("quantity (kg)"), max_digits=8, decimal_places=2)
    cost = models.DecimalField(_("cost"), max_digits=10, decimal_places=2)
    notes = models.TextField(_("notes"), blank=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("feed log")
        verbose_name_plural = _("feed logs")
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if self.feed_inventory and not self.pk:
            self.cost = self.quantity_kg * self.feed_inventory.cost_per_kg
        super().save(*args, **kwargs)

    def __str__(self):
        feed_name = self.feed_inventory.feed_type if self.feed_inventory else "No feed"
        return f"{self.batch} — {feed_name} ({self.date})"


class GrowthRecord(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='growth_records', verbose_name=_("batch"))
    date = models.DateField(_("date"))
    average_weight_kg = models.DecimalField(_("average weight (kg)"), max_digits=6, decimal_places=3)
    sample_size = models.PositiveIntegerField(_("sample size"), help_text=_("Number of animals sampled for this average"))
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("growth record")
        verbose_name_plural = _("growth records")
        ordering = ['-date']

    def __str__(self):
        return f"{self.batch} — {self.date}"


class MortalityLog(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='mortality_logs', verbose_name=_("batch"))
    date = models.DateField(_("date"))
    count = models.PositiveIntegerField(_("count"))
    cause = models.CharField(_("cause"), max_length=200, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("mortality log")
        verbose_name_plural = _("mortality logs")
        ordering = ['-date']

    def __str__(self):
        return f"{self.batch} — {self.date} — {self.count} deaths"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        batch_pk = self.batch_id
        super().save(*args, **kwargs)
        
        # Use direct SQL update instead of loading and re-saving the batch instance
        # This is faster and avoids triggering any save-related signals on Batch
        if is_new and batch_pk:
            from django.db.models import F
            Batch.objects.filter(pk=batch_pk).update(
                current_stock=models.functions.Greatest(F('current_stock') - self.count, 0)
            )


class WaterQualityLog(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='water_quality_logs', verbose_name=_("batch"))
    date = models.DateField(_("date"))
    ph_level = models.DecimalField(_("pH level"), max_digits=4, decimal_places=2, null=True, blank=True)
    temperature_c = models.DecimalField(_("temperature (°C)"), max_digits=4, decimal_places=1, null=True, blank=True)
    oxygen_level = models.DecimalField(_("oxygen level (mg/L)"), max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("water quality log")
        verbose_name_plural = _("water quality logs")
        ordering = ['-date']

    def __str__(self):
        return f"{self.batch} — {self.date}"


class VaccinationRecord(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='vaccination_records', verbose_name=_("batch"))
    date = models.DateField(_("date"))
    vaccine_name = models.CharField(_("vaccine name"), max_length=150)
    dosage = models.CharField(_("dosage"), max_length=100)
    administered_by = models.CharField(_("administered by"), max_length=150, blank=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("vaccination record")
        verbose_name_plural = _("vaccination records")
        ordering = ['-date']

    def __str__(self):
        return f"{self.batch} — {self.date} — {self.vaccine_name}"


class HealthMedicationLog(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='health_logs', verbose_name=_("batch"))
    date = models.DateField(_("date"))
    medicine_name = models.CharField(_("medicine name"), max_length=150)
    dosage = models.CharField(_("dosage"), max_length=100)
    reason = models.CharField(_("reason"), max_length=200)
    administered_by = models.CharField(_("administered by"), max_length=150, blank=True)
    photo = models.ImageField(_("photo"), upload_to='health_logs/', null=True, blank=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("health/medication log")
        verbose_name_plural = _("health/medication logs")
        ordering = ['-date']

    def __str__(self):
        return f"{self.batch} — {self.date} — {self.medicine_name}"


class DailyActivityLog(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='activity_logs', verbose_name=_("batch"))
    date = models.DateField(_("date"))
    note = models.TextField(_("note"))
    photo = models.ImageField(_("photo"), upload_to='activity_logs/', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name=_("created by"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("daily activity log")
        verbose_name_plural = _("daily activity logs")
        ordering = ['-date']

    def __str__(self):
        return f"{self.batch} — {self.date}"


class Supplier(models.Model):
    name = models.CharField(_("name"), max_length=150)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("supplier")
        verbose_name_plural = _("suppliers")
        ordering = ['name']

    def __str__(self):
        return self.name


class FeedInventory(models.Model):
    feed_type = models.CharField(_("feed type"), max_length=100)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        verbose_name=_("category"),
        null=True,
        blank=True,
        related_name='feed_inventory',
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        verbose_name=_("supplier"),
        null=True,
        blank=True,
        related_name='feed_inventory',
    )
    compatible_batches = models.ManyToManyField(
        Batch,
        blank=True,
        related_name='compatible_feed_inventory',
        verbose_name=_("compatible batches"),
        help_text=_("Batches this feed is suitable for. Based on category/species match."),
    )
    quantity_on_hand_kg = models.DecimalField(_("quantity on hand (kg)"), max_digits=8, decimal_places=2)
    cost_per_kg = models.DecimalField(_("cost per kg"), max_digits=8, decimal_places=2)
    reorder_point_kg = models.DecimalField(_("reorder point (kg)"), max_digits=8, decimal_places=2, default=0)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("feed inventory")
        verbose_name_plural = _("feed inventory")
        ordering = ['feed_type']

    @property
    def needs_reorder(self):
        return self.quantity_on_hand_kg <= self.reorder_point_kg

    def __str__(self):
        if self.category:
            return f"{self.feed_type} ({self.category.name})"
        return self.feed_type


class HarvestRecord(models.Model):
    batch = models.OneToOneField(Batch, on_delete=models.CASCADE, related_name='harvest', verbose_name=_("batch"))
    harvest_date = models.DateField(_("harvest date"))
    quantity_sold = models.PositiveIntegerField(_("quantity sold"))
    total_revenue = models.DecimalField(_("total revenue"), max_digits=12, decimal_places=2)
    notes = models.TextField(_("notes"), blank=True)
    is_sample = models.BooleanField(_("sample data"), default=False)

    class Meta:
        verbose_name = _("harvest record")
        verbose_name_plural = _("harvest records")
        ordering = ['-harvest_date']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.batch.status = 'closed'
        self.batch.save(update_fields=['status'])

    @property
    def profit(self):
        return self.total_revenue - self.batch.total_feed_cost

    def __str__(self):
        return f"{self.batch} — {self.harvest_date}"
