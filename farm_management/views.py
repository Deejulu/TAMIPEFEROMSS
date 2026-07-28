from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.db.models import Sum, Count, Q, F
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView, DetailView, UpdateView, DeleteView, CreateView

from .models import Batch, FeedLog, GrowthRecord, MortalityLog, HarvestRecord, FeedInventory, Supplier, HealthMedicationLog, VaccinationRecord, WaterQualityLog, DailyActivityLog
from .forms import BatchForm, FeedLogForm, GrowthRecordForm, MortalityLogForm, HarvestRecordForm, FeedInventoryForm, SupplierForm, SupplierUpdateForm, HealthMedicationLogForm, VaccinationRecordForm, WaterQualityLogForm, DailyActivityLogForm

from admin_dashboard.mixins import AdminRequiredMixin


class FarmManagementDashboard(AdminRequiredMixin, LoginRequiredMixin, TemplateView):
    template_name = 'farm_management/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Farm Management'
        context['total_batches'] = Batch.objects.count()
        context['active_batches'] = Batch.objects.filter(status='active').count()
        context['closed_batches'] = Batch.objects.filter(status='closed').count()
        context['recent_batches'] = Batch.objects.all().order_by('-start_date')[:5]
        context['feed_inventory_count'] = FeedInventory.objects.count()
        context['low_stock_count'] = FeedInventory.objects.filter(quantity_on_hand_kg__lte=F('reorder_point_kg')).count()
        context['recent_mortality'] = MortalityLog.objects.all().order_by('-date')[:5]
        return context


class BatchListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/batch_list.html'
    model = Batch
    context_object_name = 'batches'
    paginate_by = 20

    def get_queryset(self):
        qs = Batch.objects.annotate(
            feed_logs_count=Count('feed_logs'),
            growth_records_count=Count('growth_records'),
            mortality_logs_count=Count('mortality_logs'),
        )
        species_filter = self.request.GET.get('species', '')
        status_filter = self.request.GET.get('status', '')
        search = self.request.GET.get('search', '').strip()

        if species_filter:
            qs = qs.filter(species=species_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(name__icontains=search)

        return qs.order_by('-start_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Batches'
        context['species_choices'] = Batch.SPECIES_CHOICES
        context['status_choices'] = Batch.STATUS_CHOICES
        context['selected_species'] = self.request.GET.get('species', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')
        return context


class BatchCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/batch_form.html'
    model = Batch
    form_class = BatchForm

    def get_success_url(self):
        messages.success(self.request, f'Batch "{self.object.name}" created successfully.')
        return reverse('farm_management:batch_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Batch'
        return context


class BatchUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/batch_form.html'
    model = Batch
    form_class = BatchForm

    def get_success_url(self):
        messages.success(self.request, f'Batch "{self.object.name}" updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Batch: {self.object.name}'
        return context


class BatchDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/batch_confirm_delete.html'
    model = Batch
    context_object_name = 'batch'
    success_url = reverse_lazy('farm_management:batch_list')

    def delete(self, request, *args, **kwargs):
        batch = self.get_object()
        messages.success(request, f'Batch "{batch.name}" deleted.')
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Batch: {self.object.name}'
        return context


class BatchDetailView(AdminRequiredMixin, LoginRequiredMixin, DetailView):
    template_name = 'farm_management/batch_detail.html'
    model = Batch
    context_object_name = 'batch'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.object.name

        batch = self.object

        feed_logs = batch.feed_logs.all()
        growth_records = batch.growth_records.all()
        mortality_logs = batch.mortality_logs.all()
        health_logs = batch.health_logs.all()
        activity_logs = batch.activity_logs.all()
        water_logs = batch.water_quality_logs.all()
        vaccination_records = batch.vaccination_records.all()

        context['feed_logs'] = feed_logs.order_by('-date')[:20]
        context['growth_records'] = growth_records.order_by('-date')[:20]
        context['mortality_logs'] = mortality_logs.order_by('-date')[:20]
        context['health_logs'] = health_logs.order_by('-date')[:20]
        context['activity_logs'] = activity_logs.order_by('-date')[:20]
        context['water_logs'] = water_logs.order_by('-date')[:20]
        context['vaccination_records'] = vaccination_records.order_by('-date')[:20]

        context['total_feed_cost'] = batch.total_feed_cost
        context['mortality_rate'] = batch.mortality_rate
        context['fcr'] = batch.feed_conversion_ratio

        context['has_harvest'] = hasattr(batch, 'harvest')
        if context['has_harvest']:
            context['harvest'] = batch.harvest
            context['profit'] = batch.harvest.profit

        if batch.status == 'closed' and context['has_harvest']:
            context['revenue_per_stock'] = round(batch.harvest.total_revenue / batch.harvest.quantity_sold, 2) if batch.harvest.quantity_sold else 0
            context['cost_per_stock'] = round(batch.total_feed_cost / batch.initial_count, 2) if batch.initial_count else 0

        return context


class FeedLogCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/feed_log_form.html'
    model = FeedLog
    form_class = FeedLogForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        return initial

    def get_success_url(self):
        messages.success(self.request, 'Feed log added successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Feed Log'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context


class FeedLogUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/feed_log_form.html'
    model = FeedLog
    form_class = FeedLogForm

    def get_success_url(self):
        messages.success(self.request, 'Feed log updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Feed Log'
        return context


class FeedLogDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/feed_log_confirm_delete.html'
    model = FeedLog
    context_object_name = 'log'

    def get_success_url(self):
        messages.success(self.request, 'Feed log deleted.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Feed Log'
        return context


class GrowthRecordCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/growth_record_form.html'
    model = GrowthRecord
    form_class = GrowthRecordForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        return initial

    def get_success_url(self):
        messages.success(self.request, 'Growth record added successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Growth Record'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context


class GrowthRecordUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/growth_record_form.html'
    model = GrowthRecord
    form_class = GrowthRecordForm

    def get_success_url(self):
        messages.success(self.request, 'Growth record updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Growth Record'
        return context


class GrowthRecordDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/growth_record_confirm_delete.html'
    model = GrowthRecord
    context_object_name = 'record'

    def get_success_url(self):
        messages.success(self.request, 'Growth record deleted.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Growth Record'
        return context


class MortalityLogCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/mortality_log_form.html'
    model = MortalityLog
    form_class = MortalityLogForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        return initial

    def get_success_url(self):
        messages.success(self.request, 'Mortality log added successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Mortality Log'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context


class MortalityLogUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/mortality_log_form.html'
    model = MortalityLog
    form_class = MortalityLogForm

    def get_success_url(self):
        messages.success(self.request, 'Mortality log updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Mortality Log'
        return context


class MortalityLogDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/mortality_log_confirm_delete.html'
    model = MortalityLog
    context_object_name = 'log'

    def get_success_url(self):
        messages.success(self.request, 'Mortality log deleted.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Mortality Log'
        return context


# =============================================================================
# Phase 2: Harvest & Feed Inventory
# =============================================================================

class HarvestRecordCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/harvest_record_form.html'
    model = HarvestRecord
    form_class = HarvestRecordForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        return initial

    def get_success_url(self):
        messages.success(self.request, f'Harvest recorded for "{self.object.batch.name}". Batch closed.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Record Harvest'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except IntegrityError:
            form.add_error('batch', _('A harvest record already exists for this batch.'))
            return self.form_invalid(form)


class FeedInventoryListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/feed_inventory_list.html'
    model = FeedInventory
    context_object_name = 'inventory_items'
    paginate_by = 20

    def get_queryset(self):
        return FeedInventory.objects.all().order_by('feed_type')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Feed Inventory'
        context['low_stock_count'] = FeedInventory.objects.filter(quantity_on_hand_kg__lte=F('reorder_point_kg')).count()
        return context


class FeedInventoryCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/feed_inventory_form.html'
    model = FeedInventory
    form_class = FeedInventoryForm

    def get_success_url(self):
        messages.success(self.request, f'Feed inventory item "{self.object.feed_type}" created successfully.')
        return reverse('farm_management:feed_inventory_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Feed Inventory'
        return context


class FeedInventoryUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/feed_inventory_form.html'
    model = FeedInventory
    form_class = FeedInventoryForm

    def get_success_url(self):
        messages.success(self.request, f'Feed inventory item "{self.object.feed_type}" updated successfully.')
        return reverse('farm_management:feed_inventory_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Feed Inventory: {self.object.feed_type}'
        return context


class FeedInventoryDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/feed_inventory_confirm_delete.html'
    model = FeedInventory
    context_object_name = 'item'
    success_url = reverse_lazy('farm_management:feed_inventory_list')

    def delete(self, request, *args, **kwargs):
        item = self.get_object()
        messages.success(request, f'Feed inventory item "{item.feed_type}" deleted.')
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Feed Inventory: {self.object.feed_type}'
        return context


# =============================================================================
# Phase 3: Health, Vaccination, Water Quality, Daily Activity
# =============================================================================

class HealthMedicationLogCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/health_log_form.html'
    model = HealthMedicationLog
    form_class = HealthMedicationLogForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        return initial

    def get_success_url(self):
        messages.success(self.request, 'Health/medication log added successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Health/Medication Log'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context


class HealthMedicationLogUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/health_log_form.html'
    model = HealthMedicationLog
    form_class = HealthMedicationLogForm

    def get_success_url(self):
        messages.success(self.request, 'Health/medication log updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Health/Medication Log'
        return context


class HealthMedicationLogDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/health_log_confirm_delete.html'
    model = HealthMedicationLog
    context_object_name = 'log'

    def get_success_url(self):
        messages.success(self.request, 'Health/medication log deleted.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Health/Medication Log'
        return context


class VaccinationRecordCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/vaccination_record_form.html'
    model = VaccinationRecord
    form_class = VaccinationRecordForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        return initial

    def get_success_url(self):
        messages.success(self.request, 'Vaccination record added successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Vaccination Record'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context


class VaccinationRecordUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/vaccination_record_form.html'
    model = VaccinationRecord
    form_class = VaccinationRecordForm

    def get_success_url(self):
        messages.success(self.request, 'Vaccination record updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Vaccination Record'
        return context


class VaccinationRecordDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/vaccination_record_confirm_delete.html'
    model = VaccinationRecord
    context_object_name = 'record'

    def get_success_url(self):
        messages.success(self.request, 'Vaccination record deleted.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Vaccination Record'
        return context


class WaterQualityLogCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/water_quality_log_form.html'
    model = WaterQualityLog
    form_class = WaterQualityLogForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        return initial

    def get_success_url(self):
        messages.success(self.request, 'Water quality log added successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Water Quality Log'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context


class WaterQualityLogUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/water_quality_log_form.html'
    model = WaterQualityLog
    form_class = WaterQualityLogForm

    def get_success_url(self):
        messages.success(self.request, 'Water quality log updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Water Quality Log'
        return context


class WaterQualityLogDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/water_quality_log_confirm_delete.html'
    model = WaterQualityLog
    context_object_name = 'log'

    def get_success_url(self):
        messages.success(self.request, 'Water quality log deleted.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Water Quality Log'
        return context


class DailyActivityLogCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/activity_log_form.html'
    model = DailyActivityLog
    form_class = DailyActivityLogForm

    def get_initial(self):
        initial = super().get_initial()
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            initial['batch'] = batch_pk
        if self.request.user.is_authenticated:
            initial['created_by'] = self.request.user.pk
        return initial

    def get_success_url(self):
        messages.success(self.request, 'Daily activity log added successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Daily Activity Log'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        return context


class DailyActivityLogUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/activity_log_form.html'
    model = DailyActivityLog
    form_class = DailyActivityLogForm

    def get_success_url(self):
        messages.success(self.request, 'Daily activity log updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Daily Activity Log'
        return context


class DailyActivityLogDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/activity_log_confirm_delete.html'
    model = DailyActivityLog
    context_object_name = 'log'

    def get_success_url(self):
        messages.success(self.request, 'Daily activity log deleted.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Daily Activity Log'
        return context


# =============================================================================
# Feature 1: Batch Comparison Analytics Dashboard
# =============================================================================

class BatchAnalyticsView(AdminRequiredMixin, LoginRequiredMixin, TemplateView):
    template_name = 'farm_management/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Batch Analytics'

        batches = Batch.objects.annotate(
            annotated_total_feed_cost=Sum('feed_logs__cost'),
            annotated_total_feed_qty=Sum('feed_logs__quantity_kg'),
            annotated_total_mortality=Sum('mortality_logs__count'),
        ).prefetch_related('feed_logs', 'growth_records', 'mortality_logs', 'harvest')

        analytics = []
        for batch in batches:
            fcr = batch.feed_conversion_ratio
            growth_records = batch.growth_records.all().order_by('date')
            if growth_records.count() >= 2:
                earliest = growth_records.first()
                latest = growth_records.last()
                days = (latest.date - earliest.date).days
                weight_gain = (latest.average_weight_kg - earliest.average_weight_kg) * batch.current_stock
                growth_rate = round(float(weight_gain / days), 4) if days > 0 and weight_gain > 0 else None
            else:
                growth_rate = None

            profit = None
            if hasattr(batch, 'harvest'):
                profit = batch.harvest.profit

            analytics.append({
                'batch': batch,
                'total_feed_cost': batch.annotated_total_feed_cost or 0,
                'total_feed_qty': batch.annotated_total_feed_qty or 0,
                'fcr': fcr,
                'mortality_rate': batch.mortality_rate,
                'growth_rate': growth_rate,
                'profit': profit,
            })

        context['analytics'] = analytics

        if analytics:
            context['highest_feed'] = max(analytics, key=lambda x: x['total_feed_cost'])
            context['best_fcr'] = min(
                [a for a in analytics if a['fcr'] is not None],
                key=lambda x: x['fcr'],
            ) if any(a['fcr'] is not None for a in analytics) else None
            context['fastest_growth'] = max(
                [a for a in analytics if a['growth_rate'] is not None],
                key=lambda x: x['growth_rate'],
            ) if any(a['growth_rate'] is not None for a in analytics) else None
            context['highest_mortality'] = max(analytics, key=lambda x: x['mortality_rate'])
            context['most_profitable'] = max(
                [a for a in analytics if a['profit'] is not None],
                key=lambda x: x['profit'],
            ) if any(a['profit'] is not None for a in analytics) else None

        return context


# =============================================================================
# Feature 2: Supplier Directory CRUD
# =============================================================================

class SupplierListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/supplier_list.html'
    model = Supplier
    context_object_name = 'suppliers'
    paginate_by = 20

    def get_queryset(self):
        return Supplier.objects.annotate(
            feed_inventory_count=Count('feed_inventory'),
        ).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Suppliers'
        return context


class SupplierCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/supplier_form.html'
    model = Supplier
    form_class = SupplierForm

    def get_success_url(self):
        messages.success(self.request, f'Supplier "{self.object.name}" created successfully.')
        return reverse('farm_management:supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Supplier'
        return context


class SupplierUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/supplier_form.html'
    model = Supplier
    form_class = SupplierUpdateForm

    def get_success_url(self):
        messages.success(self.request, f'Supplier "{self.object.name}" updated successfully.')
        return reverse('farm_management:supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Supplier: {self.object.name}'
        return context


class SupplierDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/supplier_confirm_delete.html'
    model = Supplier
    context_object_name = 'supplier'
    success_url = reverse_lazy('farm_management:supplier_list')

    def delete(self, request, *args, **kwargs):
        supplier = self.get_object()
        messages.success(request, f'Supplier "{supplier.name}" deleted.')
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Supplier: {self.object.name}'
        return context


# =============================================================================
# Feature 3: PDF Batch Reports
# =============================================================================

class BatchPDFReportView(AdminRequiredMixin, LoginRequiredMixin, DetailView):
    model = Batch
    context_object_name = 'batch'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = self.object
        context['feed_logs'] = batch.feed_logs.all().order_by('-date')
        context['growth_records'] = batch.growth_records.all().order_by('-date')
        context['mortality_logs'] = batch.mortality_logs.all().order_by('-date')
        context['health_logs'] = batch.health_logs.all().order_by('-date')
        context['vaccination_records'] = batch.vaccination_records.all().order_by('-date')
        context['activity_logs'] = batch.activity_logs.all().order_by('-date')
        context['water_logs'] = batch.water_quality_logs.all().order_by('-date')
        context['has_harvest'] = hasattr(batch, 'harvest')
        if context['has_harvest']:
            context['harvest'] = batch.harvest
            context['profit'] = batch.harvest.profit
        return context

    def render_to_response(self, context, **response_kwargs):
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        batch = self.get_object()
        html = render_to_string('farm_management/batch_report_pdf.html', self.get_context_data())
        try:
            from weasyprint import HTML
            pdf = HTML(string=html).write_pdf()
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="batch_report_{batch.pk}.pdf"'
            return response
        except Exception:
            response = HttpResponse(html, content_type='text/html')
            response['Content-Disposition'] = f'attachment; filename="batch_report_{batch.pk}.html"'
            return response
