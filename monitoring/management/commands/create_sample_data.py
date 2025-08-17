# Save this as monitoring/management/commands/create_sample_data.py
# Create the directories first: monitoring/management/ and monitoring/management/commands/
# Also create __init__.py files in both directories

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from monitoring.models import Farm, Crop, Field, HarvestRecord, Inventory, UserProfile
from decimal import Decimal
from datetime import date, timedelta
import random

class Command(BaseCommand):
    help = 'Create sample data for testing the harvest monitoring system'
    
    def add_arguments(self, parser):
        parser.add_argument('--farms', type=int, default=6, help='Number of farms to create')
        parser.add_argument('--years', type=int, default=2, help='Years of historical data')
        parser.add_argument('--clear', action='store_true', help='Clear existing data first')
    
    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            HarvestRecord.objects.all().delete()
            Inventory.objects.all().delete()
            Field.objects.all().delete()
            Farm.objects.all().delete()
            Crop.objects.all().delete()
            UserProfile.objects.all().delete()
            # Don't delete User objects as they might include superuser
            
        self.stdout.write('Creating sample data for harvest monitoring system...')
        
        # Create sample users
        users = self.create_users()
        crops = self.create_crops()
        farms = self.create_farms(users['manager'], options['farms'])
        self.create_fields_and_harvests(farms, crops, users, options['years'])
        self.create_inventory_items(farms, users['manager'])
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created:\n'
                f'- {len(farms)} farms\n'
                f'- {Field.objects.count()} fields\n'
                f'- {HarvestRecord.objects.count()} harvest records\n'
                f'- {Inventory.objects.count()} inventory items\n'
                f'- {len(crops)} crop types'
            )
        )
    
    def create_users(self):
        """Create sample users with profiles"""
        # Create or get manager
        manager, created = User.objects.get_or_create(
            username='john_manager',
            defaults={
                'first_name': 'John',
                'last_name': 'Manager',
                'email': 'john@example.com'
            }
        )
        if created:
            manager.set_password('password123')
            manager.save()
        
        # Create or get supervisor
        supervisor, created = User.objects.get_or_create(
            username='jane_supervisor',
            defaults={
                'first_name': 'Jane',
                'last_name': 'Supervisor',
                'email': 'jane@example.com'
            }
        )
        if created:
            supervisor.set_password('password123')
            supervisor.save()
        
        # Create or get worker
        worker, created = User.objects.get_or_create(
            username='bob_worker',
            defaults={
                'first_name': 'Bob',
                'last_name': 'Worker',
                'email': 'bob@example.com'
            }
        )
        if created:
            worker.set_password('password123')
            worker.save()
        
        # Create profiles
        for user, role in [(manager, 'farm_manager'), (supervisor, 'field_supervisor'), (worker, 'field_worker')]:
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': role, 'phone_number': f'+234{random.randint(7000000000, 9999999999)}'}
            )
        
        self.stdout.write(f'Created/updated {User.objects.count()} users with profiles')
        
        return {
            'manager': manager,
            'supervisor': supervisor,
            'worker': worker
        }
    
    def create_crops(self):
        """Create sample crops with realistic Nigerian data"""
        crops_data = [
            ('Maize', 'Yellow Dent', 'cereal', 120, Decimal('4.5')),
            ('Rice', 'FARO 44', 'cereal', 120, Decimal('6.0')),
            ('Cassava', 'TMS 30572', 'root', 12*30, Decimal('25.0')),  # 12 months
            ('Yam', 'White Yam', 'root', 9*30, Decimal('15.0')),      # 9 months
            ('Cowpea', 'IT90K-277-2', 'legume', 75, Decimal('1.8')),
            ('Sorghum', 'ICSV 400', 'cereal', 120, Decimal('3.5')),
            ('Millet', 'SOSAT C88', 'cereal', 90, Decimal('2.5')),
            ('Sweet Potato', 'TIS 87/0087', 'root', 4*30, Decimal('12.0')), # 4 months
            ('Plantain', 'French Horn', 'fruit', 12*30, Decimal('8.0')),    # 12 months
            ('Cocoyam', 'Local variety', 'root', 9*30, Decimal('10.0')),    # 9 months
        ]
        
        crops = []
        for name, variety, crop_type, days, yield_per_hectare in crops_data:
            crop, created = Crop.objects.get_or_create(
                name=name,
                variety=variety,
                defaults={
                    'crop_type': crop_type,
                    'growing_season_days': days,
                    'expected_yield_per_hectare': yield_per_hectare,
                    'description': f'Nigerian variety of {name.lower()}'
                }
            )
            crops.append(crop)
            if created:
                self.stdout.write(f'Created crop: {crop}')
        
        return crops
    
    def create_farms(self, manager, count):
        """Create sample farms with realistic Nigerian locations"""
        farm_data = [
            ('Green Valley Farms', 'Kaduna State', 'Sandy loam', '+2348012345678'),
            ('Golden Harvest Estate', 'Kano State', 'Clay loam', '+2348087654321'),
            ('Sunshine Agriculture', 'Ogun State', 'Loamy', '+2348023456789'),
            ('River Basin Farms', 'Kebbi State', 'Alluvial', '+2348034567890'),
            ('Highland Plantation', 'Plateau State', 'Volcanic soil', '+2348045678901'),
            ('Savanna Fields Ltd', 'Niger State', 'Sandy', '+2348056789012'),
            ('Forest Edge Farms', 'Ondo State', 'Forest soil', '+2348067890123'),
            ('Delta Agriculture', 'Delta State', 'Swamp soil', '+2348078901234'),
        ]
        
        farms = []
        for i in range(count):
            name, location, soil_type, phone = farm_data[i % len(farm_data)]
            if i >= len(farm_data):
                name = f"{name} {i+1}"
            
            area = Decimal(str(random.uniform(100, 800)))
            established = date.today() - timedelta(days=random.randint(365*2, 365*10))
            
            farm, created = Farm.objects.get_or_create(
                name=name,
                defaults={
                    'manager': manager,
                    'location': location,
                    'total_area_hectares': area,
                    'description': f'Agricultural farm specializing in crop production in {location}',
                    'contact_phone': phone,
                    'contact_email': f'{name.lower().replace(" ", "")}@example.com',
                    'established_date': established,
                    'soil_type': soil_type,
                    'climate_zone': 'Tropical',
                    'water_source': random.choice(['Borehole', 'River', 'Rain-fed', 'Dam']),
                    'is_active': True
                }
            )
            farms.append(farm)
            
            if created:
                self.stdout.write(f'Created farm: {farm.name}')
        
        return farms
    
    def create_fields_and_harvests(self, farms, crops, users, years):
        """Create fields and historical harvest records"""
        supervisor = users['supervisor']
        worker = users['worker']
        
        for farm in farms:
            # Create 3-6 fields per farm
            fields_count = random.randint(3, 6)
            farm_area_per_field = farm.total_area_hectares / fields_count
            
            for i in range(fields_count):
                crop = random.choice(crops)
                field_area = farm_area_per_field * Decimal(str(random.uniform(0.8, 1.2)))
                
                # Calculate planting and harvest dates
                planting_date = date.today() - timedelta(days=random.randint(30, 300))
                if crop.growing_season_days:
                    harvest_date = planting_date + timedelta(days=crop.growing_season_days)
                else:
                    harvest_date = planting_date + timedelta(days=120)  # default
                
                field = Field.objects.create(
                    farm=farm,
                    name=f'Field {chr(65+i)}',  # Field A, B, C, etc.
                    crop=crop,
                    area_hectares=field_area,
                    planting_date=planting_date,
                    expected_harvest_date=harvest_date,
                    supervisor=supervisor,
                    soil_type=farm.soil_type,
                    irrigation_type=random.choice(['Rain-fed', 'Drip', 'Sprinkler', 'Flood']),
                    is_active=True,
                    notes=f'Field dedicated to {crop.name} production'
                )
                
                # Create historical harvest records
                for year_offset in range(years):
                    harvests_per_year = random.randint(1, 3)  # 1-3 harvests per year
                    
                    for h in range(harvests_per_year):
                        harvest_year = date.today().year - year_offset
                        harvest_month = random.randint(1, 12)
                        harvest_day = random.randint(1, 28)
                        
                        try:
                            harvest_date = date(harvest_year, harvest_month, harvest_day)
                        except ValueError:
                            harvest_date = date(harvest_year, harvest_month, 28)
                        
                        # Skip future dates
                        if harvest_date > date.today():
                            continue
                        
                        # Calculate realistic harvest quantity
                        expected_yield = crop.expected_yield_per_hectare or Decimal('5')
                        base_quantity = field_area * expected_yield
                        
                        # Add randomness: 70% to 120% of expected yield
                        variation = Decimal(str(random.uniform(0.7, 1.2)))
                        actual_quantity = base_quantity * variation
                        
                        # Quality distribution: mostly B and A grades
                        quality_weights = {'A': 25, 'B': 50, 'C': 20, 'D': 5}
                        quality_grade = random.choices(
                            list(quality_weights.keys()),
                            weights=list(quality_weights.values())
                        )[0]
                        
                        HarvestRecord.objects.create(
                            field=field,
                            harvest_date=harvest_date,
                            quantity_tons=actual_quantity,
                            quality_grade=quality_grade,
                            harvested_by=random.choice([supervisor, worker]),
                            status='completed',
                            weather_conditions=random.choice([
                                'Sunny', 'Partly Cloudy', 'Overcast', 'Light Rain', 'Clear'
                            ]),
                            moisture_content=Decimal(str(random.uniform(8, 25))),
                            notes=f'Harvest of {crop.name} from {field.name}'
                        )
    
    def create_inventory_items(self, farms, manager):
        """Create sample inventory items"""
        for farm in farms[:4]:  # Only some farms have inventory
            for field in farm.field_set.all()[:2]:  # Only some fields
                latest_harvest = field.harvestrecord_set.first()
                if latest_harvest:
                    # Store 30-70% of harvest
                    storage_percentage = Decimal(str(random.uniform(0.3, 0.7)))
                    inventory_quantity = latest_harvest.quantity_tons * storage_percentage
                    
                    storage_locations = [
                        f'{farm.name} - Main Warehouse',
                        f'{farm.name} - Storage Facility A',
                        f'{farm.name} - Cold Storage',
                        f'{farm.name} - Dry Storage Unit'
                    ]
                    
                    Inventory.objects.create(
                        crop=field.crop,
                        quantity_tons=inventory_quantity,
                        storage_location=random.choice(storage_locations),
                        storage_condition=random.choice(['dry', 'ambient', 'cold']),
                        quality_grade=latest_harvest.quality_grade,
                        date_stored=latest_harvest.harvest_date + timedelta(days=random.randint(1, 7)),
                        expiry_date=latest_harvest.harvest_date + timedelta(days=random.randint(180, 730)),
                        batch_number=f'BATCH-{random.randint(1000, 9999)}',
                        managed_by=manager,
                        harvest_record=latest_harvest,
                        unit_price=Decimal(str(random.uniform(150, 600))),  # Price per ton in Naira
                        is_reserved=random.choice([True, False]),
                        notes=f'Stored inventory from {field.name} harvest'
                    )