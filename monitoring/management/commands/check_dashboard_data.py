# Django management command to check and display real database data
# Save this as: management/commands/check_dashboard_data.py

from django.core.management.base import BaseCommand
from django.db.models import Sum, Count
from datetime import datetime, timedelta
from monitoring.models import HarvestRecord, Farm, Field, Inventory, Crop

class Command(BaseCommand):
    help = 'Check and display real dashboard data from PostgreSQL database'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Dashboard Data Verification ===\n'))
        
        # Check Farms
        farms = Farm.objects.all()
        active_farms = Farm.objects.filter(is_active=True)
        self.stdout.write(f"🏭 FARMS:")
        self.stdout.write(f"   Total Farms: {farms.count()}")
        self.stdout.write(f"   Active Farms: {active_farms.count()}")
        
        if farms.exists():
            self.stdout.write("   Farm Details:")
            for farm in farms[:5]:  # Show first 5
                self.stdout.write(f"     - {farm.name} ({'Active' if farm.is_active else 'Inactive'})")
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No farms found in database"))
        
        self.stdout.write("")
        
        # Check Crops
        crops = Crop.objects.all()
        self.stdout.write(f"🌱 CROPS:")
        self.stdout.write(f"   Total Crops: {crops.count()}")
        
        if crops.exists():
            self.stdout.write("   Crop Details:")
            for crop in crops:
                expected_yield = crop.expected_yield_per_hectare or 0
                self.stdout.write(f"     - {crop.name} (Expected: {expected_yield} tons/hectare)")
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No crops found in database"))
        
        self.stdout.write("")
        
        # Check Fields
        fields = Field.objects.all()
        active_fields = Field.objects.filter(is_active=True)
        self.stdout.write(f"🌾 FIELDS:")
        self.stdout.write(f"   Total Fields: {fields.count()}")
        self.stdout.write(f"   Active Fields: {active_fields.count()}")
        
        if fields.exists():
            total_area = sum(field.area_hectares for field in fields)
            self.stdout.write(f"   Total Area: {total_area} hectares")
            self.stdout.write("   Field Details:")
            for field in fields[:5]:  # Show first 5
                crop_name = field.crop.name if field.crop else "No crop assigned"
                self.stdout.write(f"     - {field.farm.name} / {field.name}: {field.area_hectares}ha ({crop_name})")
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No fields found in database"))
        
        self.stdout.write("")
        
        # Check Harvest Records
        harvests = HarvestRecord.objects.all()
        recent_harvests = HarvestRecord.objects.filter(
            harvest_date__gte=datetime.now().date() - timedelta(days=30)
        )
        
        self.stdout.write(f"📊 HARVEST RECORDS:")
        self.stdout.write(f"   Total Harvest Records: {harvests.count()}")
        self.stdout.write(f"   Recent Harvests (30 days): {recent_harvests.count()}")
        
        if harvests.exists():
            total_harvested = harvests.aggregate(total=Sum('quantity_tons'))['total'] or 0
            self.stdout.write(f"   Total Quantity Harvested: {total_harvested} tons")
            
            # Show harvest by crop
            harvest_by_crop = {}
            for harvest in harvests:
                crop_name = harvest.field.crop.name if harvest.field.crop else "Unknown"
                if crop_name not in harvest_by_crop:
                    harvest_by_crop[crop_name] = 0
                harvest_by_crop[crop_name] += float(harvest.quantity_tons)
            
            self.stdout.write("   Harvest by Crop:")
            for crop, quantity in harvest_by_crop.items():
                self.stdout.write(f"     - {crop}: {quantity} tons")
                
            self.stdout.write("   Recent Harvest Records:")
            for harvest in recent_harvests[:5]:  # Show first 5 recent
                self.stdout.write(f"     - {harvest.field.farm.name}/{harvest.field.name}: {harvest.quantity_tons} tons on {harvest.harvest_date}")
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No harvest records found in database"))
        
        self.stdout.write("")
        
        # Check Inventory
        inventory = Inventory.objects.all()
        self.stdout.write(f"📦 INVENTORY:")
        self.stdout.write(f"   Total Inventory Records: {inventory.count()}")
        
        if inventory.exists():
            total_inventory = inventory.aggregate(total=Sum('quantity_tons'))['total'] or 0
            self.stdout.write(f"   Total Inventory: {total_inventory} tons")
            
            self.stdout.write("   Inventory Details:")
            for inv in inventory[:5]:  # Show first 5
                crop_name = inv.crop.name if inv.crop else "Unknown crop"
                self.stdout.write(f"     - {crop_name}: {inv.quantity_tons} tons")
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No inventory records found in database"))
        
        self.stdout.write("")
        
        # Check upcoming harvests
        upcoming_date = datetime.now().date() + timedelta(days=60)
        upcoming_harvests = Field.objects.filter(
            expected_harvest_date__lte=upcoming_date,
            expected_harvest_date__gte=datetime.now().date(),
            is_active=True
        )
        
        self.stdout.write(f"📅 UPCOMING HARVESTS (Next 60 days):")
        self.stdout.write(f"   Count: {upcoming_harvests.count()}")
        
        if upcoming_harvests.exists():
            for field in upcoming_harvests:
                crop_name = field.crop.name if field.crop else "Unknown crop"
                self.stdout.write(f"     - {field.farm.name}/{field.name} ({crop_name}): {field.expected_harvest_date}")
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No upcoming harvests scheduled"))
        
        self.stdout.write("")
        
        # Summary and Recommendations
        self.stdout.write(self.style.SUCCESS("=== SUMMARY & RECOMMENDATIONS ==="))
        
        issues = []
        if not farms.exists():
            issues.append("Add farms to your database")
        if not crops.exists():
            issues.append("Add crop types to your database")
        if not fields.exists():
            issues.append("Add fields to your farms")
        if not harvests.exists():
            issues.append("Record some harvest data")
        if not upcoming_harvests.exists():
            issues.append("Set expected harvest dates for your fields")
        
        if issues:
            self.stdout.write(self.style.WARNING("To see real data in your dashboard, you need to:"))
            for i, issue in enumerate(issues, 1):
                self.stdout.write(f"   {i}. {issue}")
        else:
            self.stdout.write(self.style.SUCCESS("✅ Your database has data! The dashboard should display real information."))
        
        self.stdout.write(f"\n🔄 Dashboard Status: {'READY' if not issues else 'NEEDS DATA'}")


# Alternative: Simple function to run in Django shell
def check_dashboard_data():
    """
    Simple function to check dashboard data - run this in Django shell:
    python manage.py shell
    >>> from monitoring.views import check_dashboard_data
    >>> check_dashboard_data()
    """
    from django.db.models import Sum
    from monitoring.models import HarvestRecord, Farm, Field, Inventory, Crop
    
    print("=== Dashboard Data Check ===")
    print(f"Farms: {Farm.objects.count()} total, {Farm.objects.filter(is_active=True).count()} active")
    print(f"Crops: {Crop.objects.count()}")
    print(f"Fields: {Field.objects.count()} total, {Field.objects.filter(is_active=True).count()} active")
    print(f"Harvest Records: {HarvestRecord.objects.count()}")
    print(f"Inventory Records: {Inventory.objects.count()}")
    
    total_harvested = HarvestRecord.objects.aggregate(total=Sum('quantity_tons'))['total'] or 0
    total_inventory = Inventory.objects.aggregate(total=Sum('quantity_tons'))['total'] or 0
    
    print(f"Total Harvested: {total_harvested} tons")
    print(f"Total Inventory: {total_inventory} tons")
    
    if total_harvested == 0:
        print("⚠️  No harvest data - add some harvest records to see real data in dashboard")
    else:
        print("✅ Dashboard should display real harvest data")
        
        
        
        
      
        