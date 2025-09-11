
from django.core.management.base import BaseCommand
from monitoring.models import CropType, StorageLocation

class Command(BaseCommand):
    help = 'Populate initial inventory data (crop types and storage locations)'

    def handle(self, *args, **options):
        self.stdout.write('Starting inventory data population...')
        
        # Create Crop Types
        crop_data = [
            {
                'name': 'corn',
                'display_name': 'Corn',
                'description': 'Maize crop commonly grown for food and animal feed',
                'average_shelf_life_days': 365,
                'minimum_stock_threshold': 50.0
            },
            {
                'name': 'wheat',
                'display_name': 'Wheat',
                'description': 'Cereal grain used for making flour and bread',
                'average_shelf_life_days': 730,
                'minimum_stock_threshold': 75.0
            },
            {
                'name': 'cocoa',
                'display_name': 'Cocoa',
                'description': 'Cocoa beans used for chocolate production',
                'average_shelf_life_days': 1095,
                'minimum_stock_threshold': 25.0
            },
            {
                'name': 'rice',
                'display_name': 'Rice',
                'description': 'Staple grain crop consumed worldwide',
                'average_shelf_life_days': 1460,
                'minimum_stock_threshold': 100.0
            },
            {
                'name': 'cassava',
                'display_name': 'Cassava',
                'description': 'Root vegetable and important food source',
                'average_shelf_life_days': 90,
                'minimum_stock_threshold': 30.0
            },
            {
                'name': 'yam',
                'display_name': 'Yam',
                'description': 'Starchy root vegetable',
                'average_shelf_life_days': 120,
                'minimum_stock_threshold': 20.0
            }
        ]
        
        created_crops = 0
        for crop_info in crop_data:
            crop, created = CropType.objects.get_or_create(
                name=crop_info['name'],
                defaults={
                    'display_name': crop_info['display_name'],
                    'description': crop_info['description'],
                    'average_shelf_life_days': crop_info['average_shelf_life_days'],
                    'minimum_stock_threshold': crop_info['minimum_stock_threshold'],
                    'is_active': True
                }
            )
            if created:
                created_crops += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created crop type: {crop.display_name}')
                )
            else:
                self.stdout.write(f'Crop type already exists: {crop.display_name}')
        
        # Create Storage Locations
        storage_data = [
            {
                'name': 'Main Warehouse',
                'code': 'MW-01',
                'address': 'Central Farm Location, Main Storage Facility',
                'capacity_tons': 1000.0
            },
            {
                'name': 'Secondary Warehouse',
                'code': 'SW-01',
                'address': 'Secondary Farm Location, Backup Storage',
                'capacity_tons': 750.0
            },
            {
                'name': 'Cold Storage Unit',
                'code': 'CS-01',
                'address': 'Refrigerated Storage for Perishables',
                'capacity_tons': 500.0
            },
            {
                'name': 'Dry Storage Facility',
                'code': 'DS-01',
                'address': 'Dry Storage for Grains and Processed Goods',
                'capacity_tons': 800.0
            },
            {
                'name': 'Processing Center Storage',
                'code': 'PC-01',
                'address': 'Storage attached to processing facility',
                'capacity_tons': 400.0
            }
        ]
        
        created_locations = 0
        for location_info in storage_data:
            location, created = StorageLocation.objects.get_or_create(
                code=location_info['code'],
                defaults={
                    'name': location_info['name'],
                    'address': location_info['address'],
                    'capacity_tons': location_info['capacity_tons'],
                    'is_active': True
                }
            )
            if created:
                created_locations += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created storage location: {location.name} ({location.code})')
                )
            else:
                self.stdout.write(f'Storage location already exists: {location.name} ({location.code})')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nInventory data population completed!'
                f'\nCreated {created_crops} new crop types'
                f'\nCreated {created_locations} new storage locations'
            )
        )
        
        # Display summary
        total_crops = CropType.objects.filter(is_active=True).count()
        total_locations = StorageLocation.objects.filter(is_active=True).count()
        
        self.stdout.write(f'\nCurrent active data:')
        self.stdout.write(f'- Crop types: {total_crops}')
        self.stdout.write(f'- Storage locations: {total_locations}')
        
        self.stdout.write('\nYou can now use the inventory management system!')