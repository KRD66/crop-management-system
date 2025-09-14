# populate_database.py
# Run this script in Django shell: python3 manage.py shell < populate_database.py

from django.contrib.auth.models import User
from monitoring.models import *
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import random

print("Starting database population...")

# Create additional users if needed
users_data = [
    {'username': 'john_manager', 'email': 'john@farm.com', 'first_name': 'John', 'last_name': 'Smith'},
    {'username': 'mary_supervisor', 'email': 'mary@farm.com', 'first_name': 'Mary', 'last_name': 'Johnson'},
    {'username': 'david_worker', 'email': 'david@farm.com', 'first_name': 'David', 'last_name': 'Brown'},
]

for user_data in users_data:
    user, created = User.objects.get_or_create(
        username=user_data['username'],
        defaults={
            'email': user_data['email'],
            'first_name': user_data['first_name'],
            'last_name': user_data['last_name'],
        }
    )
    if created:
        user.set_password('password123')
        user.save()
        print(f"Created user: {user.username}")

# Create UserProfiles for new users
for user in User.objects.all():
    if not hasattr(user, 'userprofile'):
        profile = UserProfile.objects.create(
            user=user,
            role=random.choice(['farm_manager', 'field_supervisor', 'field_worker']),
            phone_number=f"+234{random.randint(7000000000, 9999999999)}",
        )
        print(f"Created profile for: {user.username}")

# Create more crops
crops_data = [
    {'name': 'Maize', 'variety': 'Yellow Corn', 'crop_type': 'cereal', 'expected_yield_per_hectare': Decimal('6.5')},
    {'name': 'Rice', 'variety': 'Ofada', 'crop_type': 'cereal', 'expected_yield_per_hectare': Decimal('4.2')},
    {'name': 'Yam', 'variety': 'White Yam', 'crop_type': 'root', 'expected_yield_per_hectare': Decimal('12.0')},
    {'name': 'Cocoa', 'variety': 'Trinitario', 'crop_type': 'other', 'expected_yield_per_hectare': Decimal('1.8')},
    {'name': 'Plantain', 'variety': 'French Horn', 'crop_type': 'fruit', 'expected_yield_per_hectare': Decimal('15.0')},
    {'name': 'Beans', 'variety': 'Cowpea', 'crop_type': 'legume', 'expected_yield_per_hectare': Decimal('2.5')},
]

for crop_data in crops_data:
    crop, created = Crop.objects.get_or_create(
        name=crop_data['name'],
        variety=crop_data['variety'],
        defaults=crop_data
    )
    if created:
        print(f"Created crop: {crop.name} - {crop.variety}")

# Create CropTypes for inventory
crop_types_data = [
    {'name': 'corn', 'display_name': 'Corn', 'average_shelf_life_days': 365, 'minimum_stock_threshold': Decimal('50.0')},
    {'name': 'rice', 'display_name': 'Rice', 'average_shelf_life_days': 730, 'minimum_stock_threshold': Decimal('100.0')},
    {'name': 'yam', 'display_name': 'Yam', 'average_shelf_life_days': 180, 'minimum_stock_threshold': Decimal('75.0')},
    {'name': 'cocoa', 'display_name': 'Cocoa', 'average_shelf_life_days': 1095, 'minimum_stock_threshold': Decimal('25.0')},
    {'name': 'plantain', 'display_name': 'Plantain', 'average_shelf_life_days': 30, 'minimum_stock_threshold': Decimal('20.0')},
    {'name': 'beans', 'display_name': 'Beans', 'average_shelf_life_days': 545, 'minimum_stock_threshold': Decimal('40.0')},
]

for crop_type_data in crop_types_data:
    crop_type, created = CropType.objects.get_or_create(
        name=crop_type_data['name'],
        defaults=crop_type_data
    )
    if created:
        print(f"Created crop type: {crop_type.display_name}")

# Create storage locations
storage_locations_data = [
    {'name': 'Central Warehouse', 'code': 'CW-01', 'capacity_tons': Decimal('500.0')},
    {'name': 'North Storage', 'code': 'NS-02', 'capacity_tons': Decimal('250.0')},
    {'name': 'South Depot', 'code': 'SD-03', 'capacity_tons': Decimal('300.0')},
    {'name': 'Cold Storage Unit', 'code': 'CS-04', 'capacity_tons': Decimal('150.0')},
]

for storage_data in storage_locations_data:
    storage, created = StorageLocation.objects.get_or_create(
        code=storage_data['code'],
        defaults=storage_data
    )
    if created:
        print(f"Created storage location: {storage.name}")

# Create more farms
farms_data = [
    {
        'name': 'Green Valley Farm',
        'location': 'Ogun State, Nigeria',
        'total_area_hectares': Decimal('45.5'),
        'description': 'Mixed crop farming focusing on maize and yam production',
        'contact_phone': '+234123456789',
    },
    {
        'name': 'Sunrise Agricultural Center',
        'location': 'Oyo State, Nigeria',
        'total_area_hectares': Decimal('62.3'),
        'description': 'Large scale rice and cocoa cultivation',
        'contact_phone': '+234987654321',
    },
    {
        'name': 'Heritage Plantations',
        'location': 'Cross River State, Nigeria',
        'total_area_hectares': Decimal('38.7'),
        'description': 'Specializing in plantain and cassava farming',
        'contact_phone': '+234555666777',
    },
]

all_users = list(User.objects.all())
for farm_data in farms_data:
    farm, created = Farm.objects.get_or_create(
        name=farm_data['name'],
        defaults={
            **farm_data,
            'manager': random.choice(all_users),
            'established_date': date.today() - timedelta(days=random.randint(365, 2000)),
            'soil_type': random.choice(['Loamy', 'Clay', 'Sandy', 'Silty']),
        }
    )
    if created:
        print(f"Created farm: {farm.name}")

# Create fields for each farm
all_farms = Farm.objects.all()
all_crops = Crop.objects.all()
all_supervisors = User.objects.all()

for farm in all_farms:
    # Create 2-4 fields per farm
    num_fields = random.randint(2, 4)
    for i in range(num_fields):
        field_name = f"Field {chr(65+i)}"  # Field A, Field B, etc.
        
        field, created = Field.objects.get_or_create(
            farm=farm,
            name=field_name,
            defaults={
                'crop': random.choice(all_crops),
                'area_hectares': Decimal(str(round(random.uniform(2.5, 15.0), 2))),
                'planting_date': date.today() - timedelta(days=random.randint(30, 200)),
                'expected_harvest_date': date.today() + timedelta(days=random.randint(10, 90)),
                'supervisor': random.choice(all_supervisors),
                'soil_quality': random.choice(['excellent', 'good', 'average']),
                'irrigation_type': random.choice(['Drip', 'Sprinkler', 'Manual', 'Rain-fed']),
            }
        )
        if created:
            print(f"Created field: {farm.name} - {field_name}")

# Create harvest records for the last 12 months
all_fields = Field.objects.all()
start_date = date.today() - timedelta(days=365)

for field in all_fields:
    # Create 3-8 harvest records per field over the year
    num_harvests = random.randint(3, 8)
    
    for i in range(num_harvests):
        harvest_date = start_date + timedelta(days=random.randint(0, 365))
        
        # Calculate realistic quantity based on field area and crop
        base_yield = float(field.crop.expected_yield_per_hectare or Decimal('5.0'))
        area = float(field.area_hectares)
        # Add some variation (80% to 120% of expected)
        variation = random.uniform(0.8, 1.2)
        quantity = round(base_yield * area * variation, 2)
        
        harvest, created = HarvestRecord.objects.get_or_create(
            field=field,
            harvest_date=harvest_date,
            defaults={
                'quantity_tons': Decimal(str(quantity)),
                'quality_grade': random.choice(['A', 'A', 'B', 'B', 'C']),  # Weighted toward better grades
                'harvested_by': random.choice(all_supervisors),
                'status': 'completed',
                'weather_conditions': random.choice(['Sunny', 'Cloudy', 'Light Rain', 'Clear']),
                'moisture_content': Decimal(str(round(random.uniform(12.0, 18.0), 2))),
                'created_by': random.choice(all_supervisors),
            }
        )
        if created:
            print(f"Created harvest: {field.farm.name} - {field.name} - {quantity}t")

# Create inventory items
all_crop_types = CropType.objects.all()
all_storage_locations = StorageLocation.objects.all()

for crop_type in all_crop_types:
    # Create 2-4 inventory batches per crop type
    num_batches = random.randint(2, 4)
    
    for i in range(num_batches):
        storage_location = random.choice(all_storage_locations)
        quantity = round(random.uniform(20.0, 150.0), 2)
        
        # Date stored in the last 6 months
        date_stored = date.today() - timedelta(days=random.randint(1, 180))
        # Expiry date based on crop shelf life
        expiry_date = date_stored + timedelta(days=crop_type.average_shelf_life_days)
        
        inventory, created = InventoryItem.objects.get_or_create(
            crop_type=crop_type,
            storage_location=storage_location,
            date_stored=date_stored,
            defaults={
                'quantity': Decimal(str(quantity)),
                'quality_grade': random.choice(['A', 'B', 'C']),
                'expiry_date': expiry_date,
                'added_by': random.choice(all_users),
            }
        )
        if created:
            print(f"Created inventory: {crop_type.display_name} - {quantity}t at {storage_location.name}")

# Update farm calculated fields
print("\nUpdating farm calculated fields...")
for farm in Farm.objects.all():
    farm.update_calculated_fields()
    print(f"Updated: {farm.name}")

print("\nDatabase population completed!")

# Print summary statistics
print("\n" + "="*50)
print("DATABASE SUMMARY")
print("="*50)
print(f"Users: {User.objects.count()}")
print(f"UserProfiles: {UserProfile.objects.count()}")
print(f"Farms: {Farm.objects.count()}")
print(f"Crops: {Crop.objects.count()}")
print(f"CropTypes: {CropType.objects.count()}")
print(f"Fields: {Field.objects.count()}")
print(f"HarvestRecords: {HarvestRecord.objects.count()}")
print(f"InventoryItems: {InventoryItem.objects.count()}")
print(f"StorageLocations: {StorageLocation.objects.count()}")

# Calculate totals for dashboard
total_harvested = HarvestRecord.objects.aggregate(total=Sum('quantity_tons'))['total'] or 0
total_inventory = InventoryItem.objects.aggregate(total=Sum('quantity'))['total'] or 0
active_farms = Farm.objects.filter(is_active=True).count()

print(f"\nDASHBOARD METRICS:")
print(f"Total Harvested: {total_harvested} tons")
print(f"Total Inventory: {total_inventory} tons")
print(f"Active Farms: {active_farms}")
print("="*50)