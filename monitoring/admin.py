# monitoring/admin.py - Fixed admin configuration
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Farm, Crop, Field, HarvestRecord, Inventory, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'phone_number', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'phone_number']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'role', 'phone_number')
        }),
        ('System Information', {
            'fields': ('supabase_id', 'is_active'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ['name', 'manager', 'location', 'total_area_hectares', 'is_active']
    list_filter = ['is_active', 'created_at', 'location']
    search_fields = ['name', 'location', 'manager__username', 'manager__first_name', 'manager__last_name']
    readonly_fields = ['created_at', 'updated_at', 'efficiency_display', 'harvest_summary']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'manager', 'location', 'total_area_hectares')
        }),
        ('Contact & Details', {
            'fields': ('contact_phone', 'contact_email', 'established_date'),
            'classes': ('collapse',)
        }),
        ('Agricultural Details', {
            'fields': ('soil_type', 'climate_zone', 'water_source', 'certifications'),
            'classes': ('collapse',)
        }),
        ('Status & Notes', {
            'fields': ('is_active', 'description', 'notes')
        }),
        ('Analytics', {
            'fields': ('efficiency_display', 'harvest_summary'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def efficiency_display(self, obj):
        """Display farm efficiency with color coding"""
        efficiency = obj.efficiency_percentage
        if efficiency >= 80:
            color = 'green'
        elif efficiency >= 60:
            color = 'orange' 
        else:
            color = 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            efficiency
        )
    efficiency_display.short_description = 'Efficiency'
    
    def harvest_summary(self, obj):
        """Display harvest summary"""
        total = obj.total_harvested_all_time
        this_year = obj.total_harvested_this_year
        return format_html(
            'Total: {} tons<br>This year: {} tons',
            total,
            this_year
        )
    harvest_summary.short_description = 'Harvest Summary'


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ['name', 'variety', 'crop_type', 'expected_yield_per_hectare', 'growing_season_days', 'is_active']
    list_filter = ['crop_type', 'is_active', 'created_at']
    search_fields = ['name', 'variety', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'variety', 'crop_type', 'is_active')
        }),
        ('Growing Information', {
            'fields': ('growing_season_days', 'expected_yield_per_hectare')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ['name', 'farm', 'crop', 'area_hectares', 'supervisor', 'is_active', 'harvest_status']
    list_filter = ['is_active', 'farm', 'crop', 'supervisor', 'planting_date']
    search_fields = ['name', 'farm__name', 'crop__name', 'supervisor__username']
    readonly_fields = ['created_at', 'updated_at', 'harvest_status', 'efficiency_display']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'farm', 'crop', 'area_hectares', 'supervisor')
        }),
        ('Dates', {
            'fields': ('planting_date', 'expected_harvest_date')
        }),
        ('Field Details', {
            'fields': ('soil_type', 'irrigation_type', 'is_active'),
            'classes': ('collapse',)
        }),
        ('Analytics', {
            'fields': ('harvest_status', 'efficiency_display'),
            'classes': ('collapse',)
        }),
        ('Notes & Timestamps', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def harvest_status(self, obj):
        """Display harvest status with days remaining"""
        days = obj.days_to_harvest
        if days is None:
            return 'No harvest date set'
        elif days == 0:
            return format_html('<span style="color: red; font-weight: bold;">Ready to harvest!</span>')
        elif days <= 7:
            return format_html('<span style="color: orange;">Ready in {} days</span>', days)
        else:
            return f'{days} days remaining'
    harvest_status.short_description = 'Harvest Status'
    
    def efficiency_display(self, obj):
        """Display field efficiency"""
        efficiency = obj.field_efficiency
        harvested = obj.total_harvested
        return format_html(
            'Efficiency: {:.1f}%<br>Harvested: {} tons',
            efficiency,
            harvested
        )
    efficiency_display.short_description = 'Performance'


@admin.register(HarvestRecord)
class HarvestRecordAdmin(admin.ModelAdmin):
    list_display = ['field', 'harvest_date', 'quantity_tons', 'quality_grade', 'harvested_by', 'status']
    list_filter = ['status', 'quality_grade', 'harvest_date', 'field__farm']
    search_fields = ['field__name', 'field__farm__name', 'harvested_by__username', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'yield_display', 'efficiency_display']
    date_hierarchy = 'harvest_date'
    
    fieldsets = (
        ('Harvest Information', {
            'fields': ('field', 'harvest_date', 'quantity_tons', 'quality_grade', 'harvested_by')
        }),
        ('Status & Conditions', {
            'fields': ('status', 'weather_conditions', 'moisture_content')
        }),
        ('Analytics', {
            'fields': ('yield_display', 'efficiency_display'),
            'classes': ('collapse',)
        }),
        ('Notes & Timestamps', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def yield_display(self, obj):
        """Display yield per hectare"""
        yield_per_ha = obj.yield_per_hectare
        return format_html('{:.2f} tons/hectare', yield_per_ha)
    yield_display.short_description = 'Yield per Hectare'
    
    def efficiency_display(self, obj):
        """Display efficiency score"""
        efficiency = obj.efficiency_score
        if efficiency >= 90:
            color = 'green'
        elif efficiency >= 70:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            efficiency
        )
    efficiency_display.short_description = 'Efficiency Score'


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['crop', 'quantity_tons', 'storage_location', 'quality_grade', 'date_stored', 'status_display']
    list_filter = ['quality_grade', 'storage_condition', 'is_reserved', 'date_stored', 'crop']
    search_fields = ['crop__name', 'storage_location', 'batch_number', 'managed_by__username']
    readonly_fields = ['created_at', 'updated_at', 'storage_duration', 'value_display', 'status_display']
    
    fieldsets = (
        ('Inventory Information', {
            'fields': ('crop', 'quantity_tons', 'quality_grade', 'batch_number')
        }),
        ('Storage Details', {
            'fields': ('storage_location', 'storage_condition', 'date_stored', 'expiry_date')
        }),
        ('Management', {
            'fields': ('managed_by', 'harvest_record', 'unit_price', 'is_reserved')
        }),
        ('Analytics', {
            'fields': ('storage_duration', 'value_display', 'status_display'),
            'classes': ('collapse',)
        }),
        ('Notes & Timestamps', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def storage_duration(self, obj):
        """Display how long item has been in storage"""
        days = obj.days_in_storage
        if days == 0:
            return 'Stored today'
        elif days == 1:
            return '1 day'
        else:
            return f'{days} days'
    storage_duration.short_description = 'Storage Duration'
    
    def value_display(self, obj):
        """Display total value if price is available"""
        total_value = obj.total_value
        if total_value:
            return format_html('₦{:,.2f}', total_value)
        return 'No price set'
    value_display.short_description = 'Total Value'
    
    def status_display(self, obj):
        """Display inventory status with alerts"""
        status_parts = []
        
        if obj.is_reserved:
            status_parts.append('<span style="color: blue;">Reserved</span>')
        
        if obj.is_expired:
            status_parts.append('<span style="color: red; font-weight: bold;">EXPIRED</span>')
        elif obj.days_until_expiry and obj.days_until_expiry <= 7:
            status_parts.append(f'<span style="color: orange;">Expires in {obj.days_until_expiry} days</span>')
        
        if obj.is_low_stock:
            status_parts.append('<span style="color: orange;">Low Stock</span>')
        
        if not status_parts:
            status_parts.append('<span style="color: green;">Good</span>')
        
        return format_html('<br>'.join(status_parts))
    status_display.short_description = 'Status'


# Customize the admin site header
admin.site.site_header = "Harvest Monitoring System Admin"
admin.site.site_title = "HMS Admin"
admin.site.index_title = "Welcome to Harvest Monitoring System Administration"