from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from datetime import date
from django.db.models import Sum, Count, Avg
from django.db.models.signals import post_save
from django.dispatch import receiver

from django.db import models
from django.utils import timezone
from django.apps import apps

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('farm_manager', 'Farm Manager'),
        ('field_supervisor', 'Field Supervisor'),
        ('field_worker', 'Field Worker'),
        ('inventory_manager', 'Inventory Manager'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='field_worker')
    supabase_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_role_display()}"

    
    # Enhanced permission properties
    @property
    def can_manage_farms(self):
        """Check if user can manage farms"""
        return self.role in ['admin', 'farm_manager']
    
    @property
    def can_track_harvests(self):
        """Check if user can track harvests"""
        return self.role in ['admin', 'farm_manager', 'field_supervisor', 'field_worker']
    
    @property
    def can_manage_inventory(self):
        """Check if user can manage inventory"""
        return self.role in ['admin', 'inventory_manager']
    
    @property
    def can_supervise_fields(self):
        """Check if user can supervise fields"""
        return self.role in ['admin', 'farm_manager', 'field_supervisor']
    
    @property
    def can_view_analytics(self):
        """Check if user can view analytics"""
        return self.role in ['admin', 'farm_manager', 'field_supervisor']
    
    @property
    def can_generate_reports(self):
        """Check if user can generate reports"""
        return self.role in ['admin', 'farm_manager', 'inventory_manager']
    
    @property
    def can_manage_users(self):
        """Check if user can manage other users"""
        return self.role == 'admin'
    
    @property
    def can_view_notifications(self):
        """Check if user can view notifications"""
        return True  # All users can view notifications
    
    def get_accessible_menu_items(self):
        """Return menu items based on user role"""
        menu_items = []
        
        # Dashboard - accessible to all roles
        menu_items.append({
            'name': 'Dashboard',
            'url': 'dashboard',
            'icon': 'dashboard'
        })
        
        # Role-specific menu items
        if self.role == 'admin':
            menu_items.extend([
                {'name': 'Farm Management', 'url': 'farm_management', 'icon': 'farm'},
                {'name': 'Harvest Tracking', 'url': 'harvest_tracking', 'icon': 'harvest'},
                {'name': 'Analytics', 'url': 'analytics', 'icon': 'analytics'},
                {'name': 'Inventory', 'url': 'inventory', 'icon': 'inventory'},
                {'name': 'Reports', 'url': 'reports', 'icon': 'reports'},
                {'name': 'Notifications', 'url': 'notifications', 'icon': 'notifications'},
                {'name': 'User Management', 'url': 'user_management', 'icon': 'users'},
            ])
        
        elif self.role == 'farm_manager':
            menu_items.extend([
                {'name': 'Farm Management', 'url': 'farm_management', 'icon': 'farm'},
                {'name': 'Harvest Tracking', 'url': 'harvest_tracking', 'icon': 'harvest'},
                {'name': 'Analytics', 'url': 'analytics', 'icon': 'analytics'},
                {'name': 'Inventory', 'url': 'inventory', 'icon': 'inventory'},
                {'name': 'Reports', 'url': 'reports', 'icon': 'reports'},
                {'name': 'Notifications', 'url': 'notifications', 'icon': 'notifications'},
            ])
        
        elif self.role == 'field_supervisor':
            menu_items.extend([
                {'name': 'Harvest Tracking', 'url': 'harvest_tracking', 'icon': 'harvest'},
                {'name': 'Analytics', 'url': 'analytics', 'icon': 'analytics'},
                {'name': 'Notifications', 'url': 'notifications', 'icon': 'notifications'},
            ])
        
        elif self.role == 'inventory_manager':
            menu_items.extend([
                {'name': 'Inventory', 'url': 'inventory', 'icon': 'inventory'},
                {'name': 'Reports', 'url': 'reports', 'icon': 'reports'},
                {'name': 'Notifications', 'url': 'notifications', 'icon': 'notifications'},
            ])
        
        elif self.role == 'field_worker':
            menu_items.extend([
                {'name': 'Harvest Tracking', 'url': 'harvest_tracking', 'icon': 'harvest'},
                {'name': 'Notifications', 'url': 'notifications', 'icon': 'notifications'},
            ])
        
        return menu_items
    
    def get_queryset_for_model(self, model_name):
        """Get filtered queryset based on user role and permissions"""
        from django.apps import apps
        
        if model_name == 'Farm':
            if self.role == 'admin':
                return Farm.objects.all()
            elif self.role == 'farm_manager':
                return Farm.objects.filter(manager=self.user)
            elif self.role in ['field_supervisor', 'field_worker']:
                # Can see farms where they supervise fields
                return Farm.objects.filter(field__supervisor=self.user).distinct()
            else:
                return Farm.objects.none()
        
        elif model_name == 'Field':
            if self.role == 'admin':
                return Field.objects.all()
            elif self.role == 'farm_manager':
                return Field.objects.filter(farm__manager=self.user)
            elif self.role in ['field_supervisor', 'field_worker']:
                return Field.objects.filter(supervisor=self.user)
            else:
                return Field.objects.none()
        
        elif model_name == 'HarvestRecord':
            if self.role == 'admin':
                return HarvestRecord.objects.all()
            elif self.role == 'farm_manager':
                return HarvestRecord.objects.filter(field__farm__manager=self.user)
            elif self.role in ['field_supervisor', 'field_worker']:
                return HarvestRecord.objects.filter(field__supervisor=self.user)
            else:
                return HarvestRecord.objects.none()
        
        elif model_name == 'Inventory':
            if self.role in ['admin', 'inventory_manager']:
                return Inventory.objects.all()
            elif self.role == 'farm_manager':
                # Farm managers can see inventory from their farms
                return Inventory.objects.filter(harvest_record__field__farm__manager=self.user)
            else:
                return Inventory.objects.none()
        
        elif model_name == 'InventoryItem':  # NEW CASE
            if self.role in ['admin', 'inventory_manager']:
                return InventoryItem.objects.all()
            elif self.role == 'farm_manager':
                # Farm managers see items added by their farm's users (via added_by or transactions)
                return InventoryItem.objects.filter(added_by__userprofile__role='farm_manager', 
                                                   added_by__userprofile__user__managed_farms__manager=self.user).distinct()
            else:
                return InventoryItem.objects.none()
        
        # Default: return empty queryset for unknown models
        return apps.get_model('your_app', model_name).objects.none()
    
    def can_access_object(self, obj):
        """Check if user can access a specific object"""
        if self.role == 'admin':
            return True
        
        if isinstance(obj, Farm):
            return (self.role == 'farm_manager' and obj.manager == self.user) or \
                   (self.role in ['field_supervisor', 'field_worker'] and 
                    obj.field_set.filter(supervisor=self.user).exists())
        
        elif isinstance(obj, Field):
            return (self.role == 'farm_manager' and obj.farm.manager == self.user) or \
                   (self.role in ['field_supervisor', 'field_worker'] and obj.supervisor == self.user)
        
        elif isinstance(obj, HarvestRecord):
            return (self.role == 'farm_manager' and obj.field.farm.manager == self.user) or \
                   (self.role in ['field_supervisor', 'field_worker'] and obj.field.supervisor == self.user)
        
        elif isinstance(obj, Inventory):
            return self.role in ['admin', 'inventory_manager'] or \
                   (self.role == 'farm_manager' and obj.harvest_record and 
                    obj.harvest_record.field.farm.manager == self.user)
        
        elif isinstance(obj, InventoryItem):  # NEW CASE
            return self.role in ['admin', 'inventory_manager'] or \
                   (self.role == 'farm_manager' and obj.added_by and 
                    obj.added_by.userprofile.role == 'farm_manager' and 
                    obj.added_by.userprofile.user.managed_farms.filter(manager=self.user).exists())
        
        return False
class Farm(models.Model):
    """
    Farm model with all required fields for admin interface
    """
    name = models.CharField(max_length=200)
    manager = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='managed_farms',
        help_text="Farm manager responsible for this farm"
    )
    location = models.CharField(max_length=200, help_text="Farm location/address")
    total_area_hectares = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total farm area in hectares"
    )
    description = models.TextField(blank=True, help_text="Farm description")
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    established_date = models.DateField(null=True, blank=True)
    soil_type = models.CharField(max_length=100, blank=True)
    climate_zone = models.CharField(max_length=100, blank=True)
    water_source = models.CharField(max_length=100, blank=True)
    certifications = models.CharField(max_length=200, blank=True, help_text="Organic, Fair Trade, etc.")
    is_active = models.BooleanField(default=True, help_text="Is this farm currently active?")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    
    # Added for template compatibility
    calculated_total_area = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, editable=False)
    calculated_field_count = models.IntegerField(default=0, editable=False)
    # ManyToMany for crop types (from template checkboxes)
    crop_types = models.ManyToManyField('CropType', blank=True, related_name='farms')
    # For yield calculations
    calculated_avg_yield = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, editable=False)
    
    class Meta:
        verbose_name = "Farm"
        verbose_name_plural = "Farms"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.location}"
    
    def save(self, *args, **kwargs):
        """Override save to update calculated fields after PK is assigned."""
        super().save(*args, **kwargs)  # Save first to get PK
        self.update_calculated_fields()  # Update calculated fields after save
    
    def update_calculated_fields(self):
        """Update calculated fields based on child fields."""
        self.calculated_total_area = self.field_set.aggregate(total=Sum('area_hectares'))['total'] or Decimal('0.00')
        self.calculated_field_count = self.field_set.count()
        # Calculate avg yield from harvests (tons per acre, convert hectares to acres)
        if self.calculated_field_count > 0:
            total_yield = self.field_set.aggregate(total=Sum('harvestrecord_set__quantity_tons'))['total'] or Decimal('0.00')
            total_acres = float(self.calculated_total_area * Decimal('2.47105'))  # hectares to acres
            self.calculated_avg_yield = (total_yield / Decimal(str(total_acres))) if total_acres > 0 else Decimal('0.00')
        else:
            self.calculated_avg_yield = Decimal('0.00')
        # Save the updates
        super().save(update_fields=['calculated_total_area', 'calculated_field_count', 'calculated_avg_yield'])
    
    @property
    def total_fields(self):
        """Get total number of fields in this farm"""
        return self.field_set.count()
    
    @property
    def active_fields(self):
        """Get number of active fields in this farm"""
        return self.field_set.filter(is_active=True).count()
    
    @property
    def total_harvested_all_time(self):
        """Get total harvest quantity for all time"""
        return self.field_set.aggregate(
            total=Sum('harvestrecord_set__quantity_tons')
        )['total'] or Decimal('0.00')
    
    @property
    def total_harvested_this_year(self):
        """Get total harvest quantity for current year"""
        current_year = timezone.now().year
        return self.field_set.aggregate(
            total=Sum('harvestrecord_set__quantity_tons', 
                     filter=models.Q(harvestrecord_set__harvest_date__year=current_year))
        )['total'] or Decimal('0.00')
    
    @property
    def efficiency_percentage(self):
        """Calculate farm efficiency as percentage of expected vs actual yield"""
        expected_total = Decimal('0')
        for field in self.field_set.all():
            if field.crop.expected_yield_per_hectare:
                expected_total += field.area_hectares * field.crop.expected_yield_per_hectare
            else:
                expected_total += field.area_hectares * Decimal('5')  # Default
        
        if expected_total > 0:
            actual_total = self.total_harvested_all_time
            return min(float((actual_total / expected_total) * 100), 100)
        return 0.0
    
    @property
    def primary_crop(self):
        """Get the most common crop type in this farm"""
        from collections import defaultdict
        crop_counts = defaultdict(int)
        for field in self.field_set.all():
            crop_counts[field.crop.name] += 1
        
        if crop_counts:
            return max(crop_counts, key=crop_counts.get)
        return 'Mixed'
    
    @property
    def total_expected_yield(self):
        """Calculate total expected yield for all fields in farm"""
        expected_total = Decimal('0')
        for field in self.field_set.all():
            if field.crop.expected_yield_per_hectare:
                expected_total += field.area_hectares * field.crop.expected_yield_per_hectare
            else:
                expected_total += field.area_hectares * Decimal('5')
        return expected_total
    
    @property
    def is_underperforming(self):
        """Check if farm is underperforming (below 70% efficiency)"""
        return self.efficiency_percentage < 70.0
    
    @property
    def upcoming_harvests(self):
        """Get fields with upcoming harvests (next 30 days)"""
        from datetime import timedelta
        from django.utils import timezone
        thirty_days = timezone.now().date() + timedelta(days=30)
        return self.field_set.filter(
            expected_harvest_date__lte=thirty_days,
            expected_harvest_date__gte=timezone.now().date(),
            is_active=True
        )
    
    def get_monthly_harvest(self, year, month):
        """Get harvest total for a specific month"""
        return self.field_set.aggregate(
            total=Sum('harvestrecord_set__quantity_tons',
                     filter=models.Q(
                         harvestrecord_set__harvest_date__year=year,
                         harvestrecord_set__harvest_date__month=month
                     ))
        )['total'] or Decimal('0.00')
class Crop(models.Model):
    CROP_TYPES = [
        ('cereal', 'Cereal'),
        ('vegetable', 'Vegetable'),
        ('fruit', 'Fruit'),
        ('legume', 'Legume'),
        ('root', 'Root Crop'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=100)
    variety = models.CharField(max_length=100, blank=True)
    crop_type = models.CharField(max_length=20, choices=CROP_TYPES, default='other')
    growing_season_days = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Average number of days from planting to harvest"
    )
    expected_yield_per_hectare = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Expected yield in tons per hectare"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Crop"
        verbose_name_plural = "Crops"
        ordering = ['name', 'variety']
    
    def __str__(self):
        return f"{self.name} - {self.variety}" if self.variety else self.name
    
    @property
    def display_name(self):
        """Get display name for crop"""
        return f"{self.name} ({self.variety})" if self.variety else self.name


class Field(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='field_set')
    name = models.CharField(max_length=100)
    crop = models.ForeignKey(Crop, on_delete=models.CASCADE)
    area_hectares = models.DecimalField(
        max_digits=8, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    planting_date = models.DateField()
    expected_harvest_date = models.DateField()
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='supervised_fields')
    soil_quality = models.CharField(max_length=50, blank=True, choices=[
        ('', 'Select quality'),
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('average', 'Average'),
        ('poor', 'Poor'),
    ])
    soil_type = models.CharField(max_length=100, blank=True)
    irrigation_type = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Field"
        verbose_name_plural = "Fields"
        ordering = ['farm__name', 'name']
        unique_together = ['farm', 'name']
    
    def __str__(self):
        return f"{self.farm.name} - {self.name}"
    
    def save(self, *args, **kwargs):
        """Trigger farm update after field save"""
        super().save(*args, **kwargs)
        self.farm.update_calculated_fields()
        self.farm.save()
    
    @property
    def days_to_harvest(self):
        """Calculate days remaining until expected harvest"""
        if self.expected_harvest_date:
            days = (self.expected_harvest_date - date.today()).days
            return max(0, days)
        return None
    
    @property
    def is_ready_for_harvest(self):
        """Check if field is ready for harvest"""
        return self.days_to_harvest is not None and self.days_to_harvest <= 7
    
    @property
    def total_harvested(self):
        """Get total harvest quantity for this field"""
        return self.harvestrecord_set.aggregate(
            total=Sum('quantity_tons')
        )['total'] or Decimal('0.00')
    
    @property
    def latest_harvest(self):
        """Get the latest harvest record for this field"""
        return self.harvestrecord_set.first()
    
    @property
    def harvest_count(self):
        """Get total number of harvests for this field"""
        return self.harvestrecord_set.count()
    
    @property
    def expected_yield_total(self):
        """Get expected total yield for this field"""
        if self.crop.expected_yield_per_hectare:
            return self.area_hectares * self.crop.expected_yield_per_hectare
        return self.area_hectares * Decimal('5')  # Default 5 tons/hectare
    
    @property
    def field_efficiency(self):
        """Calculate field efficiency percentage"""
        actual = self.total_harvested
        expected = self.expected_yield_total
        
        if expected > 0:
            return min(float((actual / expected) * 100), 100)
        return 0.0


class HarvestRecord(models.Model):
    QUALITY_GRADES = [
        ('A', 'Grade A - Premium'),
        ('B', 'Grade B - Good'),
        ('C', 'Grade C - Average'),
        ('D', 'Grade D - Below Average'),
    ]
    
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    field = models.ForeignKey(Field, on_delete=models.CASCADE, related_name='harvestrecord_set')
    harvest_date = models.DateField()
    quantity_tons = models.DecimalField(max_digits=10, decimal_places=2)
    quality_grade = models.CharField(max_length=1, choices=QUALITY_GRADES)
    harvested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='harvested_records')
    status = models.CharField(max_length=20, default='completed', choices=STATUS_CHOICES)
    weather_conditions = models.CharField(max_length=100, blank=True)
    moisture_content = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    
    # Add this field
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_harvest_records', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-harvest_date']
    
    def __str__(self):
        return f"{self.field} - {self.harvest_date} - {self.quantity_tons}t"
    
    @property
    def yield_per_hectare(self):
        """Calculate yield per hectare for this harvest"""
        if self.field.area_hectares > 0:
            return self.quantity_tons / self.field.area_hectares
        return Decimal('0.00')
    
    @property
    def quality_score(self):
        """Get numeric quality score (A=4, B=3, C=2, D=1)"""
        quality_scores = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
        return quality_scores.get(self.quality_grade, 1)
    
    @property
    def is_recent(self):
        """Check if harvest was done in the last 7 days"""
        from datetime import timedelta
        return (date.today() - self.harvest_date).days <= 7
    
    @property
    def efficiency_score(self):
        """Calculate efficiency score for this harvest"""
        expected = self.field.expected_yield_total
        if expected > 0:
            return min(float((self.quantity_tons / expected) * 100), 100)
        return 0.0
    
    @classmethod
    def get_monthly_performance(cls, year, month):
        """Get performance data for a specific month"""
        month_harvests = cls.objects.filter(
            harvest_date__year=year,
            harvest_date__month=month
        )
        
        if not month_harvests.exists():
            return 0.0
        
        total_actual = month_harvests.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        total_expected = sum(
            float(harvest.field.expected_yield_total)
            for harvest in month_harvests
        )
        
        if total_expected > 0:
            return min((total_actual / total_expected) * 100, 100)
        return 0.0
    
    @classmethod
    def get_crop_yearly_harvest(cls, crop_name, year):
        """Get total harvest for a specific crop in a year"""
        return cls.objects.filter(
            harvest_date__year=year,
            field__crop__name__icontains=crop_name
        ).aggregate(total=Sum('quantity_tons'))['total'] or 0
    
    def clean(self):
        """Validate harvest data"""
        from django.core.exceptions import ValidationError
        
        if self.harvest_date and self.harvest_date > date.today():
            raise ValidationError("Harvest date cannot be in the future.")
        
        if self.field and self.quantity_tons and self.field.area_hectares:
            # Check if yield is unreasonably high (more than 50 tons per hectare)
            yield_per_hectare = self.quantity_tons / self.field.area_hectares
            if yield_per_hectare > 50:
                raise ValidationError("Yield per hectare seems unreasonably high. Please verify the quantity.")


class Inventory(models.Model):
    STORAGE_CONDITIONS = [
        ('dry', 'Dry Storage'),
        ('cold', 'Cold Storage'),
        ('frozen', 'Frozen Storage'),
        ('controlled', 'Controlled Atmosphere'),
        ('ambient', 'Ambient Storage'),
    ]
    
    crop = models.ForeignKey(Crop, on_delete=models.CASCADE)
    quantity_tons = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    storage_location = models.CharField(max_length=200)
    storage_condition = models.CharField(
        max_length=20, 
        choices=STORAGE_CONDITIONS, 
        default='ambient'
    )
    quality_grade = models.CharField(max_length=1, choices=HarvestRecord.QUALITY_GRADES)
    date_stored = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    batch_number = models.CharField(max_length=50, blank=True)
    managed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='managed_inventory')
    harvest_record = models.ForeignKey(
        HarvestRecord, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Link to the harvest record if this inventory came from a specific harvest"
    )
    unit_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Price per ton"
    )
    is_reserved = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        ordering = ['-date_stored', 'crop__name']
    
    def __str__(self):
        return f"{self.crop} - {self.quantity_tons} tons ({self.storage_location})"
    
    @property
    def total_value(self):
        """Calculate total value of this inventory item"""
        if self.unit_price and self.quantity_tons:
            return self.unit_price * self.quantity_tons
        return None
    
    @property
    def days_in_storage(self):
        """Calculate days since stored"""
        return (date.today() - self.date_stored).days
    
    @property
    def is_expired(self):
        """Check if inventory item is expired"""
        if self.expiry_date:
            return date.today() > self.expiry_date
        return False
    
    @property
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if self.expiry_date:
            days = (self.expiry_date - date.today()).days
            return max(0, days)
        return None
    
    @property
    def is_low_stock(self):
        """Check if this is considered low stock (less than 10 tons)"""
        return self.quantity_tons < Decimal('10.00')
    
    def clean(self):
        """Validate inventory data"""
        from django.core.exceptions import ValidationError
        
        if self.expiry_date and self.expiry_date < self.date_stored:
            raise ValidationError("Expiry date cannot be before storage date.")
        
        if self.quantity_tons and self.quantity_tons < 0:
            raise ValidationError("Quantity cannot be negative.")
        
        
        
        


class ReportTemplate(models.Model):
    """Pre-configured report formats (Monthly Harvest, Yield Performance, etc.)"""
    REPORT_TYPES = [
        ("monthly_harvest_summary", "Monthly Harvest Summary"),
        ("yield_performance_report", "Yield Performance Report"),
        ("inventory_status_report", "Inventory Status Report"),
        ("farm_productivity_analysis", "Farm Productivity Analysis"),
        ("crop_performance_report", "Crop Performance Report"),
        ("financial_summary_report", "Financial Summary Report"),
    ]

    FREQUENCY_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("seasonal", "Seasonal"),
        ("yearly", "Yearly"),
    ]

    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, blank=True, null=True)
    last_generated = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.title


class GeneratedReport(models.Model):
    """Stores reports generated by users"""
    EXPORT_FORMATS = [
        ("pdf", "PDF Document"),
        ("excel", "Excel Spreadsheet"),
        ("csv", "CSV File"),
    ]

    template = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=50)  # keep copy even if template is deleted
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    from_date = models.DateField()
    to_date = models.DateField()
    export_format = models.CharField(max_length=10, choices=EXPORT_FORMATS)
    file = models.FileField(upload_to="reports/", blank=True, null=True)  # uploaded/generated file

    def __str__(self):
        return f"{self.name} ({self.export_format.upper()})"


class ReportActivityLog(models.Model):
    """Track user actions on reports (optional, for auditing)"""
    ACTIONS = [
        ("generate", "Generate"),
        ("download", "Download"),
        ("view", "View"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    report = models.ForeignKey(GeneratedReport, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTIONS)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} {self.action} {self.report.name}"


# monitoring/models.py (add these models to your existing models.py)

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta

class StorageLocation(models.Model):
    """Model for storage locations/warehouses"""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, help_text="Short code (e.g., WH-A)")
    address = models.TextField(blank=True, null=True)
    capacity_tons = models.DecimalField(max_digits=10, decimal_places=2, help_text="Maximum storage capacity in tons")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def current_usage(self):
        """Calculate current storage usage"""
        return sum(item.quantity for item in self.inventory_items.all())

    @property
    def usage_percentage(self):
        """Calculate usage percentage"""
        if self.capacity_tons > 0:
            return (self.current_usage / float(self.capacity_tons)) * 100
        return 0


class CropType(models.Model):
    """Model for different crop types"""
    CROP_CHOICES = [
        ('corn', 'Corn'),
        ('wheat', 'Wheat'),
        ('cocoa', 'Cocoa'),
        ('rice', 'Rice'),
        ('cassava', 'Cassava'),
        ('yam', 'Yam'),
        ('plantain', 'Plantain'),
        ('beans', 'Beans'),
    ]

    name = models.CharField(max_length=50, choices=CROP_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    average_shelf_life_days = models.IntegerField(default=180, help_text="Average shelf life in days")
    minimum_stock_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=100.0, 
                                                help_text="Alert when stock falls below this amount")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_name']

    def __str__(self):
        return self.display_name

class InventoryItemManager(models.Manager):
    def get_summary_stats(self):
        from django.db.models import Sum, Count
        return self.aggregate(
            total_quantity=Sum("quantity"),
            total_items=Count("id"),
        )
class InventoryItem(models.Model):
    """Main inventory model"""
    QUALITY_CHOICES = [
        ('A', 'Grade A - Premium'),
        ('B', 'Grade B - Good'),
        ('C', 'Grade C - Average'),
        ('D', 'Grade D - Below Average'),
    ]

    STATUS_CHOICES = [
        ('good', 'Good'),
        ('low_stock', 'Low Stock'),
        ('expiring', 'Expiring Soon'),
        ('expired', 'Expired'),
    ]

    crop_type = models.ForeignKey(CropType, on_delete=models.CASCADE, related_name='inventory_items')
    storage_location = models.ForeignKey(StorageLocation, on_delete=models.CASCADE, related_name='inventory_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Quantity in tons")
    quality_grade = models.CharField(max_length=1, choices=QUALITY_CHOICES)
    date_stored = models.DateField(default=date.today)
    expiry_date = models.DateField()
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='added_inventory')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # attach your custom manager properly here
    objects = InventoryItemManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['crop_type', 'storage_location']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['date_stored']),
        ]

    def __str__(self):
        return f"{self.crop_type.display_name} - {self.quantity}t @ {self.storage_location.name}"

    @property
    def status(self):
        """Calculate current status based on expiry date and stock level"""
        today = date.today()
        days_until_expiry = (self.expiry_date - today).days
        
        # Check if expired
        if days_until_expiry < 0:
            return 'expired'
        
        # Check if expiring soon (within 30 days)
        if days_until_expiry <= 30:
            return 'expiring'
        
        # Check if low stock
        if self.quantity <= self.crop_type.minimum_stock_threshold:
            return 'low_stock'
        
        return 'good'

    @property
    def days_until_expiry(self):
        """Calculate days until expiry"""
        return (self.expiry_date - date.today()).days

    @property
    def is_expired(self):
        """Check if item is expired"""
        return date.today() > self.expiry_date

    @property
    def is_expiring_soon(self):
        """Check if item is expiring within 30 days"""
        return 0 <= self.days_until_expiry <= 30


class InventoryTransaction(models.Model):
    """Model to track all inventory changes for audit trail"""
    ACTION_CHOICES = [
        ('ADD', 'Added to Inventory'),
        ('REMOVE', 'Removed from Inventory'),
        ('ADJUST', 'Quantity Adjusted'),
        ('EXPIRED', 'Marked as Expired'),
    ]

    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Quantity affected (positive or negative)")
    previous_quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Quantity before this transaction")
    new_quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Quantity after this transaction")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about this transaction")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['action_type']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.action_type} - {self.quantity}t of {self.inventory_item.crop_type.display_name} by {self.user}"

    @property
    def quantity_display(self):
        """Display quantity with appropriate sign"""
        if self.action_type in ['ADD', 'ADJUST'] and self.quantity > 0:
            return f"+{self.quantity}"
        elif self.action_type == 'REMOVE':
            return f"-{abs(self.quantity)}"
        return str(self.quantity)


# Manager class for common queries
class InventoryItemManager(models.Manager):
    def get_summary_stats(self):
        """Get summary statistics for dashboard"""
        from django.db.models import Sum, Count
        
        queryset = self.get_queryset()
        
        # Total inventory
        total_inventory = queryset.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        # Storage locations count
        storage_locations_count = StorageLocation.objects.filter(is_active=True).count()
        
        # Low stock items
        low_stock_count = 0
        expiring_count = 0
        
        for item in queryset:
            if item.status == 'low_stock':
                low_stock_count += 1
            elif item.status in ['expiring', 'expired']:
                expiring_count += 1
        
        return {
            'total_inventory': total_inventory,
            'storage_locations': storage_locations_count,
            'low_stock_items': low_stock_count,
            'expiring_items': expiring_count,
        }

    def by_crop_type(self, crop_type):
        """Filter by crop type"""
        return self.filter(crop_type__name=crop_type)

    def by_location(self, location):
        """Filter by storage location"""
        return self.filter(storage_location=location)

    def expiring_soon(self, days=30):
        """Get items expiring within specified days"""
        expiry_threshold = date.today() + timedelta(days=days)
        return self.filter(expiry_date__lte=expiry_threshold, expiry_date__gte=date.today())

    def expired(self):
        """Get expired items"""
        return self.filter(expiry_date__lt=date.today())


# Add the custom manager to InventoryItem
InventoryItem.add_to_class('objects', InventoryItemManager())



