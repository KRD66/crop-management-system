# monitoring/management/commands/create_admin_users.py
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from monitoring.models import UserProfile
from django.db import transaction


class Command(BaseCommand):
    help = 'Create admin users for the HarvestPro system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Username for the admin user',
            default='admin'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email for the admin user',
            default='admin@harvestpro.com'
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Password for the admin user',
            default='harvestpro123'
        )
        parser.add_argument(
            '--first-name',
            type=str,
            help='First name for the admin user',
            default='Admin'
        )
        parser.add_argument(
            '--last-name',
            type=str,
            help='Last name for the admin user',
            default='User'
        )
        parser.add_argument(
            '--create-demo',
            action='store_true',
            help='Create demo users with different roles',
        )

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                if options['create_demo']:
                    self.create_demo_users()
                else:
                    self.create_single_admin(options)
                    
        except Exception as e:
            raise CommandError(f'Error creating users: {e}')

    def create_single_admin(self, options):
        """Create a single admin user"""
        username = options['username']
        email = options['email']
        password = options['password']
        first_name = options['first_name']
        last_name = options['last_name']

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'User "{username}" already exists. Skipping...')
            )
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(f'User with email "{email}" already exists. Skipping...')
            )
            return

        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_superuser=True
        )

        # Create or update UserProfile
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'role': 'admin',
                'is_active': True,
            }
        )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created admin user: {username} ({email})')
        )
        self.stdout.write(f'Password: {password}')

    def create_demo_users(self):
        """Create multiple demo users with different roles"""
        demo_users = [
            {
                'username': 'admin_demo',
                'email': 'demo@harvestpro.com',
                'password': 'demo123',
                'first_name': 'Admin',
                'last_name': 'Demo',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True
            },
            {
                'username': 'farm_manager_demo',
                'email': 'manager@harvestpro.com',
                'password': 'manager123',
                'first_name': 'Farm',
                'last_name': 'Manager',
                'role': 'farm_manager',
                'is_staff': False,
                'is_superuser': False
            },
            {
                'username': 'supervisor_demo',
                'email': 'supervisor@harvestpro.com',
                'password': 'supervisor123',
                'first_name': 'Field',
                'last_name': 'Supervisor',
                'role': 'field_supervisor',
                'is_staff': False,
                'is_superuser': False
            },
            {
                'username': 'worker_demo',
                'email': 'worker@harvestpro.com',
                'password': 'worker123',
                'first_name': 'Field',
                'last_name': 'Worker',
                'role': 'field_worker',
                'is_staff': False,
                'is_superuser': False
            },
            {
                'username': 'inventory_demo',
                'email': 'inventory@harvestpro.com',
                'password': 'inventory123',
                'first_name': 'Inventory',
                'last_name': 'Manager',
                'role': 'inventory_manager',
                'is_staff': False,
                'is_superuser': False
            }
        ]

        created_count = 0
        for user_data in demo_users:
            username = user_data['username']
            email = user_data['email']

            # Check if user already exists
            if User.objects.filter(username=username).exists():
                self.stdout.write(
                    self.style.WARNING(f'User "{username}" already exists. Skipping...')
                )
                continue

            if User.objects.filter(email=email).exists():
                self.stdout.write(
                    self.style.WARNING(f'User with email "{email}" already exists. Skipping...')
                )
                continue

            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=user_data['password'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                is_staff=user_data.get('is_staff', False),
                is_superuser=user_data.get('is_superuser', False)
            )

            # Create UserProfile
            UserProfile.objects.create(
                user=user,
                role=user_data['role'],
                is_active=True,
            )

            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created {user_data["role"]} user: {username} ({email}) - Password: {user_data["password"]}'
                )
            )

        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'\nSuccessfully created {created_count} demo users!')
            )
            self.stdout.write('\nDemo Login Credentials:')
            self.stdout.write('=' * 50)
            for user_data in demo_users:
                if not User.objects.filter(username=user_data['username']).exists():
                    continue
                self.stdout.write(
                    f'{user_data["role"].title().replace("_", " ")}: '
                    f'{user_data["email"]} / {user_data["password"]}'
                )
        else:
            self.stdout.write(
                self.style.WARNING('No new users were created.')
            )