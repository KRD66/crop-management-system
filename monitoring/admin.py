from django.contrib import admin
from .models import UserProfile, Farm, Crop, Field, HarvestRecord, Inventory

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']

@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ['name', 'manager', 'location', 'total_area_hectares', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'location']

@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ['name', 'variety']
    search_fields = ['name', 'variety']

@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ['name', 'farm', 'crop', 'area_hectares', 'supervisor']
    list_filter = ['farm', 'crop']
    search_fields = ['name', 'farm__name']

@admin.register(HarvestRecord)
class HarvestRecordAdmin(admin.ModelAdmin):
    list_display = ['field', 'harvest_date', 'quantity_tons', 'quality_grade', 'harvested_by']
    list_filter = ['harvest_date', 'quality_grade', 'field__farm']
    search_fields = ['field__name', 'field__farm__name']
    date_hierarchy = 'harvest_date'

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['crop', 'quantity_tons', 'storage_location', 'quality_grade', 'date_stored']
    list_filter = ['crop', 'quality_grade', 'date_stored']
    search_fields = ['crop__name', 'storage_location']
