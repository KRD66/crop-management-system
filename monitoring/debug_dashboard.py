
from django.db.models import Sum
from monitoring.models import HarvestRecord, Farm, Field, Inventory, Crop
from datetime import datetime, timedelta
import json

def debug_dashboard_data():
    print("=== DEBUGGING DASHBOARD DATA ISSUES ===\n")
    
    # 1. Check Inventory Model
    print("1. INVENTORY DEBUG:")
    print(f"   Inventory model exists: {hasattr(Inventory, '_meta')}")
    
    # Check if we're using the right model name/app
    try:
        from django.apps import apps
        inventory_models = []
        for model in apps.get_models():
            if 'inventory' in model.__name__.lower():
                inventory_models.append(f"{model._meta.app_label}.{model.__name__}")
        
        print(f"   Found inventory-related models: {inventory_models}")
        
        # Try different possible inventory model names
        possible_names = ['Inventory', 'InventoryRecord', 'Stock', 'Storage']
        for name in possible_names:
            try:
                model = apps.get_model('monitoring', name)
                count = model.objects.count()
                print(f"   {name} records: {count}")
                if count > 0:
                    records = model.objects.all()[:3]
                    for record in records:
                        print(f"     - {record}")
            except:
                print(f"   {name} model not found")
                
    except Exception as e:
        print(f"   Error checking inventory: {e}")
    
    print("")
    
    # 2. Check what the current dashboard view returns
    print("2. DASHBOARD VIEW SIMULATION:")
    
    # Simulate the dashboard view logic
    current_date = datetime.now().date()
    twelve_months_ago = current_date - timedelta(days=365)
    
    # Calculate metrics like the view does
    total_harvested = HarvestRecord.objects.filter(
        harvest_date__gte=twelve_months_ago
    ).aggregate(total=Sum('quantity_tons'))['total'] or 0
    
    active_farms = Farm.objects.filter(is_active=True).count()
    
    # Try to get inventory total
    try:
        total_inventory = Inventory.objects.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
    except Exception as e:
        print(f"   Inventory query error: {e}")
        total_inventory = 0
    
    print(f"   Total Harvested (12mo): {total_harvested} tons")
    print(f"   Active Farms: {active_farms}")
    print(f"   Total Inventory: {total_inventory} tons")
    
    # Check harvest trends data
    harvest_trends = []
    for i in range(12):
        month_start = twelve_months_ago + timedelta(days=30*i)
        month_end = month_start + timedelta(days=30)
        
        month_total = HarvestRecord.objects.filter(
            harvest_date__gte=month_start,
            harvest_date__lt=month_end
        ).aggregate(total=Sum('quantity_tons'))['total'] or 0
        
        harvest_trends.append({
            'month': month_start.strftime('%b %y'),
            'value': float(month_total)
        })
    
    print(f"   Harvest trends data points: {len(harvest_trends)}")
    print(f"   Non-zero trend points: {len([t for t in harvest_trends if t['value'] > 0])}")
    
    # Check crop distribution
    total_crop_harvests = HarvestRecord.objects.filter(
        harvest_date__gte=twelve_months_ago
    ).aggregate(total=Sum('quantity_tons'))['total'] or 0
    
    if total_crop_harvests > 0:
        crop_stats = HarvestRecord.objects.filter(
            harvest_date__gte=twelve_months_ago
        ).values('field__crop__name').annotate(
            total_quantity=Sum('quantity_tons')
        ).order_by('-total_quantity')
        
        crop_distribution = []
        for crop in crop_stats:
            if crop['total_quantity'] and crop['field__crop__name']:
                percentage = (crop['total_quantity'] / total_crop_harvests) * 100
                if percentage >= 1:
                    crop_distribution.append({
                        'crop': crop['field__crop__name'].lower(),
                        'percentage': round(percentage, 1),
                        'quantity': float(crop['total_quantity'])
                    })
        
        print(f"   Crop distribution: {crop_distribution}")
    
    print("")
    
    # 3. Check template context data format
    print("3. TEMPLATE DATA FORMAT CHECK:")
    
    # Check if JSON serialization works
    try:
        harvest_trends_json = json.dumps(harvest_trends)
        print(f"   Harvest trends JSON length: {len(harvest_trends_json)}")
        print(f"   Sample: {harvest_trends_json[:100]}...")
    except Exception as e:
        print(f"   JSON serialization error: {e}")
    
    print("")
    
    # 4. Check database table structure
    print("4. DATABASE STRUCTURE CHECK:")
    
    # Check HarvestRecord fields
    harvest_fields = [field.name for field in HarvestRecord._meta.get_fields()]
    print(f"   HarvestRecord fields: {harvest_fields}")
    
    # Check if quantity field name is correct
    if 'quantity_tons' in harvest_fields:
        print("   ✅ quantity_tons field found")
    else:
        print("   ❌ quantity_tons field NOT found")
        print("   Available quantity fields:", [f for f in harvest_fields if 'quantity' in f.lower()])
    
    # Check Inventory fields
    try:
        inventory_fields = [field.name for field in Inventory._meta.get_fields()]
        print(f"   Inventory fields: {inventory_fields}")
        
        if 'quantity_tons' in inventory_fields:
            print("   ✅ Inventory quantity_tons field found")
        else:
            print("   ❌ Inventory quantity_tons field NOT found")
            print("   Available quantity fields:", [f for f in inventory_fields if 'quantity' in f.lower()])
            
    except Exception as e:
        print(f"   Inventory model error: {e}")
    
    print("")
    
    # 5. Check recent harvest record details
    print("5. RECENT HARVEST DETAILS:")
    recent_harvest = HarvestRecord.objects.order_by('-harvest_date').first()
    if recent_harvest:
        print(f"   Latest harvest ID: {recent_harvest.id}")
        print(f"   Farm: {recent_harvest.field.farm.name}")
        print(f"   Field: {recent_harvest.field.name}")
        print(f"   Crop: {recent_harvest.field.crop.name}")
        print(f"   Date: {recent_harvest.harvest_date}")
        print(f"   Quantity: {recent_harvest.quantity_tons}")
        print(f"   Within 12 months: {recent_harvest.harvest_date >= twelve_months_ago}")
    
    print("")
    print("=== RECOMMENDATIONS ===")
    
    recommendations = []
    
    if total_harvested == 0:
        recommendations.append("Check if HarvestRecord.quantity_tons is the correct field name")
        recommendations.append("Verify harvest dates are within the last 12 months")
    
    if total_inventory == 0:
        recommendations.append("Check Inventory model name and quantity field")
        recommendations.append("Verify inventory records exist with correct field names")
    
    if not recommendations:
        recommendations.append("Data looks good - check if dashboard view is using the enhanced version")
        recommendations.append("Check browser console for JavaScript errors")
        recommendations.append("Verify template is loading the enhanced version")
    
    for i, rec in enumerate(recommendations, 1):
        print(f"   {i}. {rec}")

# Run the debug
debug_dashboard_data()

# Additional specific inventory check
def check_inventory_models():
    print("\n=== SPECIFIC INVENTORY MODEL CHECK ===")
    from django.apps import apps
    
    # Get all models in the monitoring app
    try:
        monitoring_models = apps.get_app_config('monitoring').get_models()
        print("All models in monitoring app:")
        for model in monitoring_models:
            print(f"   - {model.__name__}")
            if 'inventory' in model.__name__.lower() or 'stock' in model.__name__.lower():
                count = model.objects.count()
                print(f"     Records: {count}")
                if count > 0:
                    # Show sample record
                    sample = model.objects.first()
                    print(f"     Sample: {sample}")
                    # Show field names
                    fields = [f.name for f in model._meta.get_fields()]
                    print(f"     Fields: {fields}")
    
    except Exception as e:
        print(f"Error: {e}")

check_inventory_models()