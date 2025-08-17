# monitoring/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal

class UserProfile(models.Model):
  
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('farm_manager', 'Farm Manager'),
        ('field_supervisor', 'Field Supervisor'),
        ('field_worker', 'Field Worker'),
        ('inventory_manager', 'Inventory Manager'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    supabase_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_role_display()}"
    
    @property
    def can_manage_farms(self):
        return self.role in ['admin', 'farm_manager']
    
    @property
    def can_track_harvests(self):
        return self.role in ['admin', 'farm_manager', 'field_supervisor', 'field_worker']
    
    @property
    def can_manage_inventory(self):
        """Check if user can manage inventory"""
        return self.role in ['admin', 'inventory_manager']


class Farm(models.Model):
    name = models.CharField(max_length=200)
    manager = models.ForeignKey(User, on_delete=models.CASCADE)
    location = models.CharField(max_length=300)
    total_area_hectares = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return self.name
    
    @property
    def total_harvested_this_season(self):
        from django.db.models import Sum
        return self.field_set.aggregate(
            total=Sum('harvestrecord__quantity_tons')
        )['total'] or Decimal('0.00')


class Crop(models.Model):
    name = models.CharField(max_length=100)
    variety = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.name} - {self.variety}" if self.variety else self.name


class Field(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    crop = models.ForeignKey(Crop, on_delete=models.CASCADE)
    area_hectares = models.DecimalField(max_digits=8, decimal_places=2)
    planting_date = models.DateField()
    expected_harvest_date = models.DateField()
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.farm.name} - {self.name}"


class HarvestRecord(models.Model):
    QUALITY_GRADES = [
        ('A', 'Grade A - Premium'),
        ('B', 'Grade B - Good'),
        ('C', 'Grade C - Average'),
        ('D', 'Grade D - Below Average'),
    ]
    
    field = models.ForeignKey(Field, on_delete=models.CASCADE)
    harvest_date = models.DateField(default=timezone.now)
    quantity_tons = models.DecimalField(max_digits=10, decimal_places=2)
    quality_grade = models.CharField(max_length=1, choices=QUALITY_GRADES)
    harvested_by = models.ForeignKey(User, on_delete=models.CASCADE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-harvest_date']
    
    def __str__(self):
        return f"{self.field} - {self.harvest_date} ({self.quantity_tons} tons)"


class Inventory(models.Model):
    crop = models.ForeignKey(Crop, on_delete=models.CASCADE)
    quantity_tons = models.DecimalField(max_digits=10, decimal_places=2)
    storage_location = models.CharField(max_length=200)
    quality_grade = models.CharField(max_length=1, choices=HarvestRecord.QUALITY_GRADES)
    date_stored = models.DateField(default=timezone.now)
    managed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.crop} - {self.quantity_tons} tons ({self.storage_location})"