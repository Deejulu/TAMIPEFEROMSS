from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Batch, FeedLog, GrowthRecord, MortalityLog, HarvestRecord, FeedInventory, Supplier, HealthMedicationLog, VaccinationRecord, DailyActivityLog, Species, Category, WaterQualityLog


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ['name', 'species', 'initial_count', 'start_date', 'season']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Catfish Batch - July 2026'
            }),
            'species': forms.Select(attrs={'class': 'form-select'}),
            'initial_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'season': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active species in the dropdown
        self.fields['species'].queryset = Species.objects.filter(is_active=True)


class FeedLogForm(forms.ModelForm):
    class Meta:
        model = FeedLog
        fields = ['batch', 'date', 'feed_inventory', 'quantity_kg', 'notes']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'feed_inventory': forms.Select(attrs={'class': 'form-select'}),
            'quantity_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if batch and batch.status == 'closed':
            raise forms.ValidationError(_('Cannot log feed for a closed batch.'))
        return batch

    def clean(self):
        cleaned_data = super().clean()
        batch = cleaned_data.get('batch')
        feed_inventory = cleaned_data.get('feed_inventory')

        if batch and feed_inventory:
            batch_category = batch.species.category
            feed_category = feed_inventory.category

            if feed_category and batch_category and feed_category != batch_category:
                raise forms.ValidationError(
                    _('This feed is intended for %(feed_cat)s but the selected batch is %(batch_cat)s — please select a matching feed item.') % {
                        'feed_cat': feed_category.name,
                        'batch_cat': batch_category.name,
                    }
                )

        return cleaned_data


class GrowthRecordForm(forms.ModelForm):
    class Meta:
        model = GrowthRecord
        fields = ['batch', 'date', 'average_weight_kg', 'sample_size']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'average_weight_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0'
            }),
            'sample_size': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
        }

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if batch and batch.status == 'closed':
            raise forms.ValidationError(_('Cannot log growth records for a closed batch.'))
        return batch


class MortalityLogForm(forms.ModelForm):
    class Meta:
        model = MortalityLog
        fields = ['batch', 'date', 'count', 'cause', 'notes']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'cause': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Disease, predation, water quality'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if batch and batch.status == 'closed':
            raise forms.ValidationError(_('Cannot log mortality for a closed batch.'))
        return batch

    def clean(self):
        cleaned_data = super().clean()
        batch = cleaned_data.get('batch')
        count = cleaned_data.get('count')
        if batch and count and count > batch.current_stock:
            raise forms.ValidationError(
                _("Mortality count (%(count)s) cannot exceed current stock (%(stock)s).") %
                {'count': count, 'stock': batch.current_stock}
            )
        return cleaned_data


class HarvestRecordForm(forms.ModelForm):
    class Meta:
        model = HarvestRecord
        fields = ['batch', 'harvest_date', 'quantity_sold', 'total_revenue', 'notes']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'harvest_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'quantity_sold': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'total_revenue': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        batch = cleaned_data.get('batch')
        quantity_sold = cleaned_data.get('quantity_sold')
        if batch and quantity_sold and quantity_sold > batch.current_stock:
            raise forms.ValidationError(
                _("Quantity sold (%(qty)s) cannot exceed current stock (%(stock)s).") %
                {'qty': quantity_sold, 'stock': batch.current_stock}
            )
        return cleaned_data


class FeedInventoryForm(forms.ModelForm):
    class Meta:
        model = FeedInventory
        fields = ['feed_type', 'category', 'supplier', 'quantity_on_hand_kg', 'cost_per_kg', 'reorder_point_kg', 'compatible_batches']
        widgets = {
            'feed_type': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Coppens 4mm'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={
                'class': 'form-select',
                'placeholder': 'Select supplier'
            }),
            'quantity_on_hand_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'cost_per_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'reorder_point_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['category'].required = False
        self.fields['compatible_batches'].queryset = Batch.objects.filter(status='active').order_by('-start_date')
        self.fields['compatible_batches'].help_text = "Select batches this feed is suitable for. Batches are grouped by species and category."


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'phone', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Supplier name'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone number'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email address'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Physical address'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Additional notes'
            }),
        }


class SupplierUpdateForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'phone', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Supplier name'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone number'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email address'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Physical address'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Additional notes'
            }),
        }


class HealthMedicationLogForm(forms.ModelForm):
    class Meta:
        model = HealthMedicationLog
        fields = ['batch', 'date', 'medicine_name', 'dosage', 'reason', 'administered_by', 'photo']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'medicine_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Medicine name'
            }),
            'dosage': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 10mg/kg'
            }),
            'reason': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Reason for treatment'
            }),
            'administered_by': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Who administered (optional)'
            }),
            'photo': forms.ClearableFileInput(attrs={
                'class': 'form-control'
            }),
        }

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if batch and batch.status == 'closed':
            raise forms.ValidationError(_('Cannot log health/medication for a closed batch.'))
        return batch


class VaccinationRecordForm(forms.ModelForm):
    class Meta:
        model = VaccinationRecord
        fields = ['batch', 'date', 'vaccine_name', 'dosage', 'administered_by']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'vaccine_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Vaccine name'
            }),
            'dosage': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 0.5ml per bird'
            }),
            'administered_by': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Who administered (optional)'
            }),
        }

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if batch and batch.status == 'closed':
            raise forms.ValidationError(_('Cannot log vaccination for a closed batch.'))
        if batch and batch.is_fish:
            raise forms.ValidationError(_('Vaccination records are only for poultry batches.'))
        return batch


class DailyActivityLogForm(forms.ModelForm):
    class Meta:
        model = DailyActivityLog
        fields = ['batch', 'date', 'note', 'photo']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'note': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the activity...'
            }),
            'photo': forms.ClearableFileInput(attrs={
                'class': 'form-control'
            }),
        }

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if batch and batch.status == 'closed':
            raise forms.ValidationError(_('Cannot log activity for a closed batch.'))
        return batch


class SpeciesForm(forms.ModelForm):
    class Meta:
        model = Species
        fields = ['name', 'category']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Species name (e.g. Catfish, Broiler)'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active categories in the dropdown
        self.fields['category'].queryset = Category.objects.filter(is_active=True)


class SpeciesUpdateForm(forms.ModelForm):
    class Meta:
        model = Species
        fields = ['name', 'category', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Species name (e.g. Catfish, Broiler)'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active categories in the dropdown
        self.fields['category'].queryset = Category.objects.filter(is_active=True)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Category name (e.g. Fish, Poultry, Livestock)'
            }),
        }


class CategoryUpdateForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Category name (e.g. Fish, Poultry, Livestock)'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class WaterQualityLogForm(forms.ModelForm):
    class Meta:
        model = WaterQualityLog
        fields = ['batch', 'date', 'ph_level', 'temperature_c', 'oxygen_level', 'notes']
        widgets = {
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'ph_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'e.g. 7.2'
            }),
            'temperature_c': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'placeholder': 'e.g. 28.5'
            }),
            'oxygen_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'e.g. 6.5'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any notes on water quality...'
            }),
        }

    def clean_batch(self):
        batch = self.cleaned_data.get('batch')
        if batch and batch.status == 'closed':
            raise forms.ValidationError(_('Cannot log water quality for a closed batch.'))
        return batch
