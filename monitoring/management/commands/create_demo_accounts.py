# monitoring/management/commands/create_demo_accounts.py
# Create the directory structure: monitoring/management/commands/

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from monitoring.models import UserProfile

class Command(BaseCommand):
    help = 'Create demo accounts for HarvestPro system'

    def handle(self, *args, **options):
        demo_users = [
            {
                'username': 'admin_demo',
                'email': 'demo@harvestpro.com',
                'password': 'demo123',
                'first_name': 'Admin',
                'last_name': 'Demo',
                'role': 'admin'
            },
            {
                'username': 'manager_demo',
                'email': 'manager@harvestpro.com',
                'password': 'manager123',
                'first_name': 'Manager',
                'last_name': 'Demo',
                'role': 'farm_manager'
            },
            {
                'username': 'supervisor_demo',
                'email': 'supervisor@harvestpro.com',
                'password': 'supervisor123',
                'first_name': 'Supervisor',
                'last_name': 'Demo',
                'role': 'field_supervisor'
            },
            {
                'username': 'worker_demo',
                'email': 'worker@harvestpro.com',
                'password': 'worker123',
                'first_name': 'Worker',
                'last_name': 'Demo',
                'role': 'field_worker'
            },
            {
                'username': 'inventory_demo',
                'email': 'inventory@harvestpro.com',
                'password': 'inventory123',
                'first_name': 'Inventory',
                'last_name': 'Demo',
                'role': 'inventory_manager'
            }
        ]

        created_count = 0
        updated_count = 0

        for user_data in demo_users:
            try:
                # Check if user exists
                user, created = User.objects.get_or_create(
                    username=user_data['username'],
                    defaults={
                        'email': user_data['email'],
                        'first_name': user_data['first_name'],
                        'last_name': user_data['last_name'],
                        'is_active': True
                    }
                )

                if created:
                    user.set_password(user_data['password'])
                    user.save()
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Created user: {user_data['username']}")
                    )
                else:
                    # Update existing user
                    user.email = user_data['email']
                    user.first_name = user_data['first_name']
                    user.last_name = user_data['last_name']
                    user.set_password(user_data['password'])
                    user.is_active = True
                    user.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"⚠ Updated existing user: {user_data['username']}")
                    )

                # Create or update UserProfile
                profile, profile_created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'role': user_data['role'],
                        'is_active': True
                    }
                )

                if not profile_created:
                    profile.role = user_data['role']
                    profile.is_active = True
                    profile.save()

                # Display account details
                self.stdout.write(f"  Email: {user_data['email']}")
                self.stdout.write(f"  Password: {user_data['password']}")
                self.stdout.write(f"  Role: {profile.get_role_display()}")
                self.stdout.write("")

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ Error creating {user_data['username']}: {str(e)}")
                )

        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n📊 Summary:"))
        self.stdout.write(f"  • Created: {created_count} new users")
        self.stdout.write(f"  • Updated: {updated_count} existing users")
        self.stdout.write(f"  • Total: {created_count + updated_count} demo accounts ready")
        
        self.stdout.write(self.style.SUCCESS(f"\n🎉 Demo accounts are ready to use!"))
        self.stdout.write("You can now test the login functionality with any of the accounts above.")


# monitoring/management/commands/reset_demo_data.py
# Optional: Command to reset all demo data

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from monitoring.models import UserProfile, Farm, Field, Crop, HarvestRecord, Inventory

class Command(BaseCommand):
    help = 'Reset all demo data and recreate demo accounts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete all data',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    "This will delete ALL data in the database!\n"
                    "Run with --confirm to proceed: python manage.py reset_demo_data --confirm"
                )
            )
            return

        self.stdout.write("🗑️  Deleting all existing data...")
        
        # Delete in order to respect foreign key constraints
        HarvestRecord.objects.all().delete()
        Inventory.objects.all().delete()
        Field.objects.all().delete()
        Farm.objects.all().delete()
        Crop.objects.all().delete()
        UserProfile.objects.all().delete()
        User.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("✓ All data deleted"))

        # Create demo accounts
        from django.core.management import call_command
        self.stdout.write("👥 Creating demo accounts...")
        call_command('create_demo_accounts')

        # Create sample crops
        self.stdout.write("🌾 Creating sample crops...")
        sample_crops = [
            {'name': 'Corn', 'variety': 'Sweet Corn', 'crop_type': 'cereal', 'expected_yield_per_hectare': 8.5, 'growing_season_days': 120},
            {'name': 'Wheat', 'variety': 'Winter Wheat', 'crop_type': 'cereal', 'expected_yield_per_hectare': 6.2, 'growing_season_days': 200},
            {'name': 'Soybeans', 'variety': 'GMO Roundup Ready', 'crop_type': 'legume', 'expected_yield_per_hectare': 3.8, 'growing_season_days': 130},
            {'name': 'Rice', 'variety': 'Jasmine', 'crop_type': 'cereal', 'expected_yield_per_hectare': 7.5, 'growing_season_days': 150},
            {'name': 'Cassava', 'variety': 'TMS 30572', 'crop_type': 'root', 'expected_yield_per_hectare': 25.0, 'growing_season_days': 360},
            {'name': 'Yam', 'variety': 'White Yam', 'crop_type': 'root', 'expected_yield_per_hectare': 15.0, 'growing_season_days': 280},
        ]

        for crop_data in sample_crops:
            crop, created = Crop.objects.get_or_create(
                name=crop_data['name'],
                variety=crop_data['variety'],
                defaults=crop_data
            )
            if created:
                self.stdout.write(f"  ✓ Created crop: {crop.name} - {crop.variety}")

        self.stdout.write(self.style.SUCCESS(f"\n🎉 Demo environment reset complete!"))
        self.stdout.write("You can now start fresh with clean demo data.")