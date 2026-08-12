from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.management import call_command
from django.db import IntegrityError
from django.db.models import Sum, Count, F
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView, DetailView, UpdateView, DeleteView, CreateView
from django.db.models.functions import TruncMonth
import io
from contextlib import redirect_stdout

from .models import Batch, FeedLog, GrowthRecord, MortalityLog, HarvestRecord, FeedInventory, Supplier, HealthMedicationLog, VaccinationRecord, DailyActivityLog, Species, Category
from .forms import BatchForm, FeedLogForm, GrowthRecordForm, MortalityLogForm, HarvestRecordForm, FeedInventoryForm, SupplierForm, SupplierUpdateForm, HealthMedicationLogForm, VaccinationRecordForm, DailyActivityLogForm, SpeciesForm, SpeciesUpdateForm, CategoryForm, CategoryUpdateForm

from admin_dashboard.mixins import AdminRequiredMixin
from admin_dashboard.views import log_audit

User = get_user_model()


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
        context['is_super_admin'] = self.request.user.role == User.Role.SUPER_ADMIN
        return context


class BatchListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/batch_list.html'
    model = Batch
    context_object_name = 'batches'
    paginate_by = 20

    def get_queryset(self):
        qs = Batch.objects.select_related('species').annotate(
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
        context['species_list'] = Species.objects.filter(is_active=True).order_by('category__name', 'name')
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
        log_audit(self.request, 'create', 'Batch', self.object.pk, f'Created batch "{self.object.name}" ({self.object.species})')
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
        log_audit(self.request, 'update', 'Batch', self.object.pk, f'Updated batch "{self.object.name}" ({self.object.species})')
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
        log_audit(self.request, 'delete', 'Batch', batch.pk, f'Deleted batch "{batch.name}" ({batch.species})')
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
        vaccination_records = batch.vaccination_records.all()

        context['feed_logs'] = feed_logs.order_by('-date')[:20]
        context['growth_records'] = growth_records.order_by('-date')[:20]
        context['mortality_logs'] = mortality_logs.order_by('-date')[:20]
        context['health_logs'] = health_logs.order_by('-date')[:20]
        context['activity_logs'] = activity_logs.order_by('-date')[:20]
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

    def form_valid(self, form):
        feed_inventory = form.cleaned_data.get('feed_inventory')
        quantity_kg = form.cleaned_data.get('quantity_kg')

        if feed_inventory and quantity_kg:
            if feed_inventory.quantity_on_hand_kg < quantity_kg:
                form.add_error('quantity_kg',
                    _('Not enough feed in stock — only %(available)s kg available.') % {
                        'available': feed_inventory.quantity_on_hand_kg
                    })
                return self.form_invalid(form)

        response = super().form_valid(form)

        if feed_inventory and quantity_kg:
            feed_inventory.quantity_on_hand_kg = F('quantity_on_hand_kg') - quantity_kg
            feed_inventory.save(update_fields=['quantity_on_hand_kg'])

        log_audit(self.request, 'create', 'FeedLog', self.object.pk, f'Created feed log for {self.object.batch.name}: {self.object.quantity_kg}kg')
        return response

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

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self._original_feed_inventory = obj.feed_inventory
        self._original_quantity_kg = obj.quantity_kg
        return obj

    def form_valid(self, form):
        old_feed_inventory = getattr(self, '_original_feed_inventory', self.object.feed_inventory)
        old_quantity_kg = getattr(self, '_original_quantity_kg', self.object.quantity_kg)
        new_feed_inventory = form.cleaned_data.get('feed_inventory')
        new_quantity_kg = form.cleaned_data.get('quantity_kg')

        if new_feed_inventory and new_quantity_kg is not None:
            if new_feed_inventory.quantity_on_hand_kg + old_quantity_kg < new_quantity_kg:
                form.add_error('quantity_kg',
                    _('Not enough feed in stock — only %(available)s kg available.') % {
                        'available': new_feed_inventory.quantity_on_hand_kg + old_quantity_kg
                    })
                return self.form_invalid(form)

        response = super().form_valid(form)

        if old_feed_inventory and old_quantity_kg:
            old_feed_inventory.quantity_on_hand_kg = F('quantity_on_hand_kg') + old_quantity_kg
            old_feed_inventory.save(update_fields=['quantity_on_hand_kg'])

        if new_feed_inventory and new_quantity_kg:
            new_feed_inventory.quantity_on_hand_kg = F('quantity_on_hand_kg') - new_quantity_kg
            new_feed_inventory.save(update_fields=['quantity_on_hand_kg'])

        log_audit(self.request, 'update', 'FeedLog', self.object.pk, f'Updated feed log for {self.object.batch.name}: {old_quantity_kg}kg → {new_quantity_kg}kg')
        return response

    def get_success_url(self):
        messages.success(self.request, 'Feed log updated successfully.')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Edit Feed Log'
        context['batch'] = self.object.batch
        return context


class FeedLogDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'farm_management/feed_log_confirm_delete.html'
    model = FeedLog
    context_object_name = 'log'

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        feed_inventory = self.object.feed_inventory
        quantity_kg = self.object.quantity_kg
        batch_pk = self.object.batch.pk
        log_audit(self.request, 'delete', 'FeedLog', self.object.pk, f'Deleted feed log for {self.object.batch.name}')
        response = super().delete(request, *args, **kwargs)

        if feed_inventory and quantity_kg:
            feed_inventory.quantity_on_hand_kg = F('quantity_on_hand_kg') + quantity_kg
            feed_inventory.save(update_fields=['quantity_on_hand_kg'])

        messages.success(request, 'Feed log deleted.')
        return redirect(reverse('farm_management:batch_detail', kwargs={'pk': batch_pk}))

    def get_success_url(self):
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
        log_audit(self.request, 'create', 'GrowthRecord', self.object.pk, f'Created growth record for {self.object.batch.name}: {self.object.average_weight_kg}kg')
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
        log_audit(self.request, 'update', 'GrowthRecord', self.object.pk, f'Updated growth record for {self.object.batch.name}: {self.object.average_weight_kg}kg')
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
        log_audit(self.request, 'delete', 'GrowthRecord', self.object.pk, f'Deleted growth record for {self.object.batch.name}')
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
        log_audit(self.request, 'create', 'MortalityLog', self.object.pk, f'Created mortality log for {self.object.batch.name}: {self.object.count} deaths')
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
        log_audit(self.request, 'update', 'MortalityLog', self.object.pk, f'Updated mortality log for {self.object.batch.name}: {self.object.count} deaths')
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
        log_audit(self.request, 'delete', 'MortalityLog', self.object.pk, f'Deleted mortality log for {self.object.batch.name}')
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
            response = super().form_valid(form)
        except IntegrityError:
            form.add_error('batch', _('A harvest record already exists for this batch.'))
            return self.form_invalid(form)
        log_audit(self.request, 'create', 'HarvestRecord', self.object.pk, f'Recorded harvest for {self.object.batch.name}: {self.object.quantity_sold} sold')
        return response


class FeedInventoryListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/feed_inventory_list.html'
    model = FeedInventory
    context_object_name = 'inventory_items'
    paginate_by = 20

    def get_queryset(self):
        return FeedInventory.objects.select_related('category', 'supplier').all().order_by('feed_type')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Feed Inventory'
        context['low_stock_count'] = FeedInventory.objects.filter(quantity_on_hand_kg__lte=F('reorder_point_kg')).count()
        context['unassigned_count'] = FeedInventory.objects.filter(category__isnull=True).count()
        return context


class FeedInventoryCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/feed_inventory_form.html'
    model = FeedInventory
    form_class = FeedInventoryForm

    def get_success_url(self):
        messages.success(self.request, f'Feed inventory item "{self.object.feed_type}" created successfully.')
        log_audit(self.request, 'create', 'FeedInventory', self.object.pk, f'Created feed inventory "{self.object.feed_type}"')
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
        log_audit(self.request, 'update', 'FeedInventory', self.object.pk, f'Updated feed inventory "{self.object.feed_type}"')
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
        log_audit(self.request, 'delete', 'FeedInventory', item.pk, f'Deleted feed inventory "{item.feed_type}"')
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
        log_audit(self.request, 'create', 'HealthMedicationLog', self.object.pk, f'Created health log for {self.object.batch.name}: {self.object.medicine_name}')
        if self.kwargs.get('batch_pk'):
            return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})
        return reverse('farm_management:health_records_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Health/Medication Log'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        else:
            context['batch'] = None
        return context


class HealthMedicationLogUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/health_log_form.html'
    model = HealthMedicationLog
    form_class = HealthMedicationLogForm

    def get_success_url(self):
        messages.success(self.request, 'Health/medication log updated successfully.')
        log_audit(self.request, 'update', 'HealthMedicationLog', self.object.pk, f'Updated health log for {self.object.batch.name}: {self.object.medicine_name}')
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
        log_audit(self.request, 'delete', 'HealthMedicationLog', self.object.pk, f'Deleted health log for {self.object.batch.name}')
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
        log_audit(self.request, 'create', 'VaccinationRecord', self.object.pk, f'Created vaccination record for {self.object.batch.name}: {self.object.vaccine_name}')
        if self.kwargs.get('batch_pk'):
            return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})
        return reverse('farm_management:health_records_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Vaccination Record'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        else:
            context['batch'] = None
        return context


class VaccinationRecordUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/vaccination_record_form.html'
    model = VaccinationRecord
    form_class = VaccinationRecordForm

    def get_success_url(self):
        messages.success(self.request, 'Vaccination record updated successfully.')
        log_audit(self.request, 'update', 'VaccinationRecord', self.object.pk, f'Updated vaccination record for {self.object.batch.name}: {self.object.vaccine_name}')
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
        log_audit(self.request, 'delete', 'VaccinationRecord', self.object.pk, f'Deleted vaccination record for {self.object.batch.name}')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Vaccination Record'
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
        log_audit(self.request, 'create', 'DailyActivityLog', self.object.pk, f'Created daily activity log for {self.object.batch.name}: {self.object.note[:50]}')
        if self.kwargs.get('batch_pk'):
            return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})
        return reverse('farm_management:daily_activities_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Daily Activity Log'
        batch_pk = self.kwargs.get('batch_pk')
        if batch_pk:
            context['batch'] = get_object_or_404(Batch, pk=batch_pk)
        else:
            context['batch'] = None
        return context


class DailyActivityLogUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/activity_log_form.html'
    model = DailyActivityLog
    form_class = DailyActivityLogForm

    def get_success_url(self):
        messages.success(self.request, 'Daily activity log updated successfully.')
        log_audit(self.request, 'update', 'DailyActivityLog', self.object.pk, f'Updated daily activity log for {self.object.batch.name}')
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
        log_audit(self.request, 'delete', 'DailyActivityLog', self.object.pk, f'Deleted daily activity log for {self.object.batch.name}')
        return reverse('farm_management:batch_detail', kwargs={'pk': self.object.batch.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Delete Daily Activity Log'
        return context


# =============================================================================
# Health Records List View
# =============================================================================

class HealthRecordsListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/health_records_list.html'
    context_object_name = 'records'
    paginate_by = 20

    def get_queryset(self):
        # Combine health logs and vaccination records
        from django.db.models import Q, Value, CharField
        from itertools import chain
        
        batch_filter = self.request.GET.get('batch', '')
        date_from = self.request.GET.get('date_from', '')
        date_to = self.request.GET.get('date_to', '')
        record_type = self.request.GET.get('record_type', '')
        
        health_qs = HealthMedicationLog.objects.select_related('batch', 'batch__species').all()
        vaccination_qs = VaccinationRecord.objects.select_related('batch', 'batch__species').all()
        
        if batch_filter:
            health_qs = health_qs.filter(batch_id=batch_filter)
            vaccination_qs = vaccination_qs.filter(batch_id=batch_filter)
        
        if date_from:
            health_qs = health_qs.filter(date__gte=date_from)
            vaccination_qs = vaccination_qs.filter(date__gte=date_from)
        
        if date_to:
            health_qs = health_qs.filter(date__lte=date_to)
            vaccination_qs = vaccination_qs.filter(date__lte=date_to)
        
        # Add record type annotation
        health_qs = health_qs.annotate(record_type=Value('health', output_field=CharField()))
        vaccination_qs = vaccination_qs.annotate(record_type=Value('vaccination', output_field=CharField()))
        
        if record_type == 'health':
            combined = list(health_qs)
        elif record_type == 'vaccination':
            combined = list(vaccination_qs)
        else:
            combined = list(chain(health_qs, vaccination_qs))
        
        # Sort by date descending
        combined.sort(key=lambda x: x.date, reverse=True)
        
        return combined

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Health Records'
        context['batches'] = Batch.objects.filter(status='active').order_by('-start_date')
        context['selected_batch'] = self.request.GET.get('batch', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['selected_record_type'] = self.request.GET.get('record_type', '')
        
        # Count records
        health_count = HealthMedicationLog.objects.count()
        vaccination_count = VaccinationRecord.objects.count()
        context['health_count'] = health_count
        context['vaccination_count'] = vaccination_count
        context['total_count'] = health_count + vaccination_count
        
        return context


# =============================================================================
# Daily Activities List View
# =============================================================================

class DailyActivitiesListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/daily_activities_list.html'
    model = DailyActivityLog
    context_object_name = 'activities'
    paginate_by = 20

    def get_queryset(self):
        qs = DailyActivityLog.objects.select_related('batch', 'batch__species', 'created_by').all()
        
        batch_filter = self.request.GET.get('batch', '')
        date_from = self.request.GET.get('date_from', '')
        date_to = self.request.GET.get('date_to', '')
        
        if batch_filter:
            qs = qs.filter(batch_id=batch_filter)
        
        if date_from:
            qs = qs.filter(date__gte=date_from)
        
        if date_to:
            qs = qs.filter(date__lte=date_to)
        
        return qs.order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Daily Activities'
        context['batches'] = Batch.objects.filter(status='active').order_by('-start_date')
        context['selected_batch'] = self.request.GET.get('batch', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['total_count'] = DailyActivityLog.objects.count()
        
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
        import json
        from decimal import Decimal
        
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Batch Analytics'

        batches = Batch.objects.annotate(
            annotated_total_feed_cost=Sum('feed_logs__cost'),
            annotated_total_feed_qty=Sum('feed_logs__quantity_kg'),
            annotated_total_mortality=Sum('mortality_logs__count'),
        ).prefetch_related('feed_logs', 'growth_records', 'mortality_logs', 'harvest')

        analytics = []
        analytics_json = []
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

            item = {
                'batch': batch,
                'total_feed_cost': batch.annotated_total_feed_cost or 0,
                'total_feed_qty': batch.annotated_total_feed_qty or 0,
                'fcr': fcr,
                'mortality_rate': batch.mortality_rate,
                'growth_rate': growth_rate,
                'profit': profit,
            }
            analytics.append(item)
            
            analytics_json.append({
                'batch': {
                    'name': batch.name,
                    'pk': batch.pk,
                },
                'total_feed_cost': float(item['total_feed_cost']) if item['total_feed_cost'] else 0,
                'total_feed_qty': float(item['total_feed_qty']) if item['total_feed_qty'] else 0,
                'fcr': float(fcr) if fcr else None,
                'mortality_rate': float(batch.mortality_rate) if batch.mortality_rate else 0,
                'growth_rate': float(growth_rate) if growth_rate is not None else None,
                'profit': float(profit) if profit is not None else None,
            })

        context['analytics'] = analytics
        context['analytics_json'] = json.dumps(analytics_json)

        # Pie chart data: feed cost distribution
        feed_cost_pie = []
        for item in analytics:
            feed_cost_pie.append({
                'name': item['batch'].name,
                'value': float(item['total_feed_cost']) if item['total_feed_cost'] else 0,
            })
        context['feed_cost_pie_json'] = json.dumps(feed_cost_pie)

        # Pie chart data: stock distribution
        stock_pie = []
        for item in analytics:
            stock_pie.append({
                'name': item['batch'].name,
                'value': item['batch'].current_stock,
            })
        context['stock_pie_json'] = json.dumps(stock_pie)

        # Trend line data: monthly feed cost over time
        monthly_feed = FeedLog.objects.annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            total_cost=Sum('cost')
        ).order_by('month')
        
        trend_labels = []
        trend_values = []
        for entry in monthly_feed:
            if entry['month']:
                trend_labels.append(entry['month'].strftime('%b %Y'))
                trend_values.append(float(entry['total_cost']) if entry['total_cost'] else 0)
        
        context['trend_labels_json'] = json.dumps(trend_labels)
        context['trend_values_json'] = json.dumps(trend_values)

        # Vaccination Coverage data
        vaccination_coverage = []
        vaccination_coverage_json = []
        for batch in batches:
            total_stock = batch.current_stock or 0
            vaccination_records = batch.vaccination_records.all()
            vaccinations_count = vaccination_records.count()
            coverage_pct = round((vaccinations_count / total_stock * 100), 1) if total_stock > 0 else 0
            item = {
                'batch': batch,
                'vaccinations_count': vaccinations_count,
                'total_stock': total_stock,
                'coverage_pct': coverage_pct,
            }
            vaccination_coverage.append(item)
            vaccination_coverage_json.append({
                'batch': batch.name,
                'vaccinations_count': vaccinations_count,
                'total_stock': total_stock,
                'coverage_pct': coverage_pct,
            })
        context['vaccination_coverage'] = vaccination_coverage
        context['vaccination_coverage_json'] = json.dumps(vaccination_coverage_json)

        # Health/Medication Log Frequency data
        health_log_frequency = []
        health_log_frequency_json = []
        health_reasons_data = {}
        health_medicines_data = {}
        for batch in batches:
            health_logs = batch.health_logs.all()
            log_count = health_logs.count()
            item = {
                'batch': batch,
                'log_count': log_count,
            }
            health_log_frequency.append(item)
            health_log_frequency_json.append({
                'batch': batch.name,
                'log_count': log_count,
            })
            for log in health_logs:
                reason = log.reason.strip().title() if log.reason else 'Unknown'
                medicine = log.medicine_name.strip().title() if log.medicine_name else 'Unknown'
                health_reasons_data[reason] = health_reasons_data.get(reason, 0) + 1
                health_medicines_data[medicine] = health_medicines_data.get(medicine, 0) + 1
        context['health_log_frequency'] = health_log_frequency
        context['health_log_frequency_json'] = json.dumps(health_log_frequency_json)

        # Top health reasons (pie chart)
        sorted_reasons = sorted(health_reasons_data.items(), key=lambda x: x[1], reverse=True)[:8]
        context['health_reasons_json'] = json.dumps([{'reason': r[0], 'count': r[1]} for r in sorted_reasons])

        # Top medications used (pie chart)
        sorted_medicines = sorted(health_medicines_data.items(), key=lambda x: x[1], reverse=True)[:8]
        context['health_medicines_json'] = json.dumps([{'medicine': m[0], 'count': m[1]} for m in sorted_medicines])

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
        log_audit(self.request, 'create', 'Supplier', self.object.pk, f'Created supplier "{self.object.name}"')
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
        log_audit(self.request, 'update', 'Supplier', self.object.pk, f'Updated supplier "{self.object.name}"')
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
        log_audit(self.request, 'delete', 'Supplier', supplier.pk, f'Deleted supplier "{supplier.name}"')
        messages.success(request, f'Supplier "{supplier.name}" deleted.')
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Supplier: {self.object.name}'
        return context


# =============================================================================
# Species Management CRUD
# =============================================================================

class SpeciesListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/species_list.html'
    model = Species
    context_object_name = 'species_list'
    paginate_by = 20

    def get_queryset(self):
        return Species.objects.annotate(
            batch_count=Count('batches'),
        ).order_by('category__name', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Species Management'
        return context


class SpeciesCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/species_form.html'
    model = Species
    form_class = SpeciesForm

    def get_success_url(self):
        messages.success(self.request, f'Species "{self.object.name}" created successfully.')
        log_audit(self.request, 'create', 'Species', self.object.pk, f'Created species "{self.object.name}" in {self.object.category.name}')
        return reverse('farm_management:species_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Species'
        return context


class SpeciesUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/species_form.html'
    model = Species
    form_class = SpeciesUpdateForm

    def get_success_url(self):
        messages.success(self.request, f'Species "{self.object.name}" updated successfully.')
        log_audit(self.request, 'update', 'Species', self.object.pk, f'Updated species "{self.object.name}" in {self.object.category.name}')
        return reverse('farm_management:species_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Species: {self.object.name}'
        return context


class SpeciesDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    """
    This view deactivates species instead of deleting them to preserve existing batch data.
    """
    template_name = 'farm_management/species_confirm_delete.html'
    model = Species
    context_object_name = 'species'

    def get_success_url(self):
        return reverse_lazy('farm_management:species_list')

    def form_valid(self, form):
        self.object = self.get_object()
        success_url = self.get_success_url()
        species_count = self.object.species.count()

        if species_count > 0:
            self.object.is_active = False
            self.object.save(update_fields=['is_active'])
            log_audit(self.request, 'toggle', 'Species', self.object.pk, f'Deactivated species "{self.object.name}" (used in {species_count} batch(es))')
            messages.success(self.request, f'Species "{self.object.name}" has been deactivated (used in {species_count} batch(es)). Existing batches are preserved.')
        else:
            species_name = self.object.name
            self.object.delete()
            log_audit(self.request, 'delete', 'Species', self.object.pk, f'Deleted species "{species_name}"')
            messages.success(self.request, f'Species "{species_name}" has been deleted.')

        return redirect(success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Species: {self.object.name}'
        context['batch_count'] = self.object.batches.count()
        return context


# =============================================================================
# Category Management CRUD
# =============================================================================

class CategoryListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'farm_management/category_list.html'
    model = Category
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        return Category.objects.annotate(
            species_count=Count('species'),
        ).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Category Management'
        return context


class CategoryCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'farm_management/category_form.html'
    model = Category
    form_class = CategoryForm

    def get_success_url(self):
        messages.success(self.request, f'Category "{self.object.name}" created successfully.')
        log_audit(self.request, 'create', 'Category', self.object.pk, f'Created category "{self.object.name}"')
        return reverse('farm_management:category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Category'
        return context


class CategoryUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'farm_management/category_form.html'
    model = Category
    form_class = CategoryUpdateForm

    def get_success_url(self):
        messages.success(self.request, f'Category "{self.object.name}" updated successfully.')
        log_audit(self.request, 'update', 'Category', self.object.pk, f'Updated category "{self.object.name}"')
        return reverse('farm_management:category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Category: {self.object.name}'
        return context


class CategoryDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    """
    This view deactivates categories instead of deleting them to preserve existing species/batch data.
    """
    template_name = 'farm_management/category_confirm_delete.html'
    model = Category
    context_object_name = 'category'

    def get_success_url(self):
        return reverse_lazy('farm_management:category_list')

    def form_valid(self, form):
        self.object = self.get_object()
        success_url = self.get_success_url()

        species_count = self.object.species.count()

        if species_count > 0:
            self.object.is_active = False
            self.object.save(update_fields=['is_active'])
            log_audit(self.request, 'toggle', 'Category', self.object.pk, f'Deactivated category "{self.object.name}" (used in {species_count} species)')
            messages.success(self.request, f'Category "{self.object.name}" has been deactivated (used in {species_count} species). Existing species and batches are preserved.')
        else:
            category_name = self.object.name
            self.object.delete()
            log_audit(self.request, 'delete', 'Category', self.object.pk, f'Deleted category "{category_name}"')
            messages.success(self.request, f'Category "{category_name}" has been deleted.')

        return redirect(success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Category: {self.object.name}'
        context['species_count'] = self.object.species.count()
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
        context['has_harvest'] = hasattr(batch, 'harvest')
        if context['has_harvest']:
            context['harvest'] = batch.harvest
            context['profit'] = batch.harvest.profit
        return context

    def render_to_response(self, context, **response_kwargs):
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from io import BytesIO
        from xhtml2pdf import pisa
        batch = self.get_object()
        html = render_to_string('farm_management/batch_report_pdf.html', self.get_context_data())
        pdf_io = BytesIO()
        pisa.CreatePDF(html, dest=pdf_io, encoding='UTF-8')
        pdf = pdf_io.getvalue()
        if pdf:
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="batch_report_{batch.pk}.pdf"'
            return response
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="batch_report_{batch.pk}.html"'
        return response


# =============================================================================
# Sample Data Management Views
# =============================================================================

@require_POST
def populate_sample_data(request):
    """
    Populate the farm_management app with realistic sample data.
    Restricted to Super Admin only.
    """
    if not request.user.is_authenticated or request.user.role != User.Role.SUPER_ADMIN:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Only Super Admins can populate sample data.'}, status=403)
        messages.error(request, 'Only Super Admins can populate sample data.')
        return redirect('farm_management:dashboard')

    output = io.StringIO()
    with redirect_stdout(output):
        call_command('populate_sample')

    output_text = output.getvalue()
    categories_count = output_text.count('Created category:')
    species_count = output_text.count('Created species:')
    suppliers_count = output_text.count('Created supplier:')
    feed_count = output_text.count('Created feed inventory:')
    batches_count = output_text.count('Created batch:')

    msg = (
        f'Sample data populated: {categories_count} categories, '
        f'{species_count} species, {suppliers_count} suppliers, '
        f'{feed_count} feed inventory items, {batches_count} batches.'
    )
    messages.success(request, msg)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'categories_created': categories_count,
            'species_created': species_count,
            'suppliers_created': suppliers_count,
            'feed_inventory_created': feed_count,
            'batches_created': batches_count,
            'message': msg,
        })

    return redirect('farm_management:dashboard')


@require_POST
def delete_sample_data(request):
    """
    Delete all farm_management sample data (is_sample=True).
    Restricted to Super Admin only.
    """
    if not request.user.is_authenticated or request.user.role != User.Role.SUPER_ADMIN:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Only Super Admins can delete sample data.'}, status=403)
        messages.error(request, 'Only Super Admins can delete sample data.')
        return redirect('farm_management:dashboard')

    output = io.StringIO()
    with redirect_stdout(output):
        call_command('delete_sample')

    output_text = output.getvalue()

    messages.success(request, f'Sample data deleted. {output_text.strip()}')
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f'Sample data deleted. {output_text.strip()}',
        })
    return redirect('farm_management:dashboard')
