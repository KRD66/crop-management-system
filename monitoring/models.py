from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from datetime import date
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
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
    
    class Meta:
        verbose_name = "Farm"
        verbose_name_plural = "Farms"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.location}"
    
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
            total=Sum('harvestrecord__quantity_tons')
        )['total'] or Decimal('0.00')
    
    @property
    def total_harvested_this_year(self):
        """Get total harvest quantity for current year"""
        current_year = timezone.now().year
        return self.field_set.aggregate(
            total=Sum('harvestrecord__quantity_tons', 
                     filter=models.Q(harvestrecord__harvest_date__year=current_year))
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
        thirty_days = date.today() + timedelta(days=30)
        return self.field_set.filter(
            expected_harvest_date__lte=thirty_days,
            expected_harvest_date__gte=date.today(),
            is_active=True
        )
    
    def get_monthly_harvest(self, year, month):
        """Get harvest total for a specific month"""
        return self.field_set.aggregate(
            total=Sum('harvestrecord__quantity_tons',
                     filter=models.Q(
                         harvestrecord__harvest_date__year=year,
                         harvestrecord__harvest_date__month=month
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
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE)
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
    
    field = models.ForeignKey(Field, on_delete=models.CASCADE)
    harvest_date = models.DateField(default=timezone.now)
    quantity_tons = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    quality_grade = models.CharField(max_length=1, choices=QUALITY_GRADES)
    harvested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='harvests_done')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    weather_conditions = models.CharField(max_length=200, blank=True)
    moisture_content = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Moisture content percentage"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Harvest Record"
        verbose_name_plural = "Harvest Records"
        ordering = ['-harvest_date', '-created_at']
    
    def __str__(self):
        return f"{self.field} - {self.harvest_date} ({self.quantity_tons} tons)"
    
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
        
        
        
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create UserProfile with default role when User is created"""
    if created:
        UserProfile.objects.create(user=instance, role='field_worker')

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if hasattr(instance, 'userprofile'):
        instance.userprofile.save()
    else:
        UserProfile.objects.create(user=instance, role='field_worker')        