from django.urls import path

from . import views

app_name = 'farm_management'

urlpatterns = [
    path('dashboard/', views.FarmManagementDashboard.as_view(), name='dashboard'),
    path('batches/', views.BatchListView.as_view(), name='batch_list'),
    path('batches/add/', views.BatchCreateView.as_view(), name='batch_add'),
    path('batches/<int:pk>/', views.BatchDetailView.as_view(), name='batch_detail'),
    path('batches/<int:pk>/edit/', views.BatchUpdateView.as_view(), name='batch_edit'),
    path('batches/<int:pk>/delete/', views.BatchDeleteView.as_view(), name='batch_delete'),
    path('batches/<int:pk>/report/', views.BatchPDFReportView.as_view(), name='batch_report'),

    path('analytics/', views.BatchAnalyticsView.as_view(), name='analytics'),

    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/add/', views.SupplierCreateView.as_view(), name='supplier_add'),
    path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.SupplierDeleteView.as_view(), name='supplier_delete'),

    path('species/', views.SpeciesListView.as_view(), name='species_list'),
    path('species/add/', views.SpeciesCreateView.as_view(), name='species_add'),
    path('species/<int:pk>/edit/', views.SpeciesUpdateView.as_view(), name='species_edit'),
    path('species/<int:pk>/delete/', views.SpeciesDeleteView.as_view(), name='species_delete'),

    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/add/', views.CategoryCreateView.as_view(), name='category_add'),
    path('categories/<int:pk>/edit/', views.CategoryUpdateView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', views.CategoryDeleteView.as_view(), name='category_delete'),

    path('batches/<int:batch_pk>/feed-logs/add/', views.FeedLogCreateView.as_view(), name='feed_log_add'),
    path('feed-logs/<int:pk>/edit/', views.FeedLogUpdateView.as_view(), name='feed_log_edit'),
    path('feed-logs/<int:pk>/delete/', views.FeedLogDeleteView.as_view(), name='feed_log_delete'),

    path('batches/<int:batch_pk>/growth/add/', views.GrowthRecordCreateView.as_view(), name='growth_add'),
    path('growth/<int:pk>/edit/', views.GrowthRecordUpdateView.as_view(), name='growth_edit'),
    path('growth/<int:pk>/delete/', views.GrowthRecordDeleteView.as_view(), name='growth_delete'),

    path('batches/<int:batch_pk>/mortality/add/', views.MortalityLogCreateView.as_view(), name='mortality_add'),
    path('mortality/<int:pk>/edit/', views.MortalityLogUpdateView.as_view(), name='mortality_edit'),
    path('mortality/<int:pk>/delete/', views.MortalityLogDeleteView.as_view(), name='mortality_delete'),

    path('batches/<int:batch_pk>/harvest/', views.HarvestRecordCreateView.as_view(), name='harvest_add'),
    path('feed-inventory/', views.FeedInventoryListView.as_view(), name='feed_inventory_list'),
    path('feed-inventory/add/', views.FeedInventoryCreateView.as_view(), name='feed_inventory_add'),
    path('feed-inventory/<int:pk>/edit/', views.FeedInventoryUpdateView.as_view(), name='feed_inventory_edit'),
    path('feed-inventory/<int:pk>/delete/', views.FeedInventoryDeleteView.as_view(), name='feed_inventory_delete'),

    path('batches/<int:batch_pk>/health-logs/add/', views.HealthMedicationLogCreateView.as_view(), name='health_log_add'),
    path('health-logs/<int:pk>/edit/', views.HealthMedicationLogUpdateView.as_view(), name='health_log_edit'),
    path('health-logs/<int:pk>/delete/', views.HealthMedicationLogDeleteView.as_view(), name='health_log_delete'),

    path('batches/<int:batch_pk>/vaccinations/add/', views.VaccinationRecordCreateView.as_view(), name='vaccination_add'),
    path('vaccinations/<int:pk>/edit/', views.VaccinationRecordUpdateView.as_view(), name='vaccination_edit'),
    path('vaccinations/<int:pk>/delete/', views.VaccinationRecordDeleteView.as_view(), name='vaccination_delete'),

    path('vaccinations/add/', views.VaccinationRecordCreateView.as_view(), name='vaccination_add_top'),

    path('health-records/', views.HealthRecordsListView.as_view(), name='health_records_list'),
    path('health-logs/add/', views.HealthMedicationLogCreateView.as_view(), name='health_log_add_top'),

    path('batches/<int:batch_pk>/activity-logs/add/', views.DailyActivityLogCreateView.as_view(), name='activity_log_add'),
    path('activity-logs/<int:pk>/edit/', views.DailyActivityLogUpdateView.as_view(), name='activity_log_edit'),
    path('activity-logs/<int:pk>/delete/', views.DailyActivityLogDeleteView.as_view(), name='activity_log_delete'),
    path('activity-logs/add/', views.DailyActivityLogCreateView.as_view(), name='activity_log_add_top'),

    path('daily-activities/', views.DailyActivitiesListView.as_view(), name='daily_activities_list'),

    path('sample-data/load/', views.populate_sample_data, name='populate_sample_data'),
    path('sample-data/clear/', views.delete_sample_data, name='delete_sample_data'),
]
