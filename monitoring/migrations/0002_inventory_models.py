# Create this file as: monitoring/migrations/0002_inventory_models.py
# Run: python manage.py makemigrations monitoring
# Then: python manage.py migrate

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
import datetime


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('monitoring', '0001_initial'),  # Adjust based on your existing migrations
    ]

    operations = [
        # Create StorageLocation model
        migrations.CreateModel(
            name='StorageLocation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('code', models.CharField(help_text='Short code (e.g., WH-A)', max_length=10, unique=True)),
                ('address', models.TextField(blank=True, null=True)),
                ('capacity_tons', models.DecimalField(decimal_places=2, help_text='Maximum storage capacity in tons', max_digits=10)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),

        # Create CropType model
        migrations.CreateModel(
            name='CropType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(choices=[('corn', 'Corn'), ('wheat', 'Wheat'), ('cocoa', 'Cocoa'), ('rice', 'Rice'), ('cassava', 'Cassava'), ('yam', 'Yam'), ('plantain', 'Plantain'), ('beans', 'Beans')], max_length=50, unique=True)),
                ('display_name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, null=True)),
                ('average_shelf_life_days', models.IntegerField(default=180, help_text='Average shelf life in days')),
                ('minimum_stock_threshold', models.DecimalField(decimal_places=2, default=100.0, help_text='Alert when stock falls below this amount', max_digits=10)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['display_name'],
            },
        ),

        # Create InventoryItem model
        migrations.CreateModel(
            name='InventoryItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=2, help_text='Quantity in tons', max_digits=10)),
                ('quality_grade', models.CharField(choices=[('A', 'Grade A - Premium'), ('B', 'Grade B - Good'), ('C', 'Grade C - Average'), ('D', 'Grade D - Below Average')], max_length=1)),
                ('date_stored', models.DateField(default=datetime.date.today)),
                ('expiry_date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('added_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='added_inventory', to=settings.AUTH_USER_MODEL)),
                ('crop_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inventory_items', to='monitoring.croptype')),
                ('storage_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inventory_items', to='monitoring.storagelocation')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),

        # Create InventoryTransaction model
        migrations.CreateModel(
            name='InventoryTransaction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('ADD', 'Added to Inventory'), ('REMOVE', 'Removed from Inventory'), ('ADJUST', 'Quantity Adjusted'), ('EXPIRED', 'Marked as Expired')], max_length=10)),
                ('quantity', models.DecimalField(decimal_places=2, help_text='Quantity affected (positive or negative)', max_digits=10)),
                ('previous_quantity', models.DecimalField(decimal_places=2, help_text='Quantity before this transaction', max_digits=10)),
                ('new_quantity', models.DecimalField(decimal_places=2, help_text='Quantity after this transaction', max_digits=10)),
                ('notes', models.TextField(blank=True, help_text='Additional notes about this transaction', null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('inventory_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='monitoring.inventoryitem')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),

        # Add database indexes
        migrations.AddIndex(
            model_name='inventoryitem',
            index=models.Index(fields=['crop_type', 'storage_location'], name='monitoring_i_crop_ty_b6b89a_idx'),
        ),
        migrations.AddIndex(
            model_name='inventoryitem',
            index=models.Index(fields=['expiry_date'], name='monitoring_i_expiry__cc8f44_idx'),
        ),
        migrations.AddIndex(
            model_name='inventoryitem',
            index=models.Index(fields=['date_stored'], name='monitoring_i_date_st_a4d67f_idx'),
        ),
        migrations.AddIndex(
            model_name='inventorytransaction',
            index=models.Index(fields=['timestamp'], name='monitoring_i_timesta_a8b2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='inventorytransaction',
            index=models.Index(fields=['action_type'], name='monitoring_i_action__d4e5f6_idx'),
        ),
        migrations.AddIndex(
            model_name='inventorytransaction',
            index=models.Index(fields=['user'], name='monitoring_i_user_id_g7h8i9_idx'),
        ),
    ]