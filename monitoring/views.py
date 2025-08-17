# monitoring/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import Extract
from datetime import datetime, timedelta
from .models import Farm, HarvestRecord, Inventory, Crop, Field
from collections import defaultdict
from decimal import Decimal
import json

def dashboard(request):
    """
    Dashboard view that calculates all metrics shown in your Figma design
    """
    
    # Calculate Total Harvested (like 22,600 tons in your design)
    total_harvested = HarvestRecord.objects.aggregate(
        total=Sum('quantity_tons')
    )['total'] or 0
    
    # Calculate Active Farms (like 12 in your design)
    active_farms = Farm.objects.filter(is_active=True).count()
    
    # Calculate Total Inventory (like 15,600 tons in your design)  
    total_inventory = Inventory.objects.aggregate(
        total=Sum('quantity_tons')
    )['total'] or 0
    
    # Calculate Average Yield Efficiency (simplified calculation)
    # This compares actual harvest vs expected based on field area
    fields_with_harvests = Field.objects.filter(
        harvestrecord__isnull=False
    ).distinct()
    
    if fields_with_harvests.exists():
        total_actual = HarvestRecord.objects.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        total_expected_area = fields_with_harvests.aggregate(
            total=Sum('area_hectares')
        )['total'] or 1
        # Assuming 5 tons per hectare as baseline
        avg_yield_efficiency = min(int((total_actual / (total_expected_area * 5)) * 100), 100)
    else:
        avg_yield_efficiency = 85  # Default value when no data
    
    # Get Harvest Trends data (monthly data for line chart)
    harvest_trends = []
    current_year = datetime.now().year
    
    for month in range(1, 13):
        month_total = HarvestRecord.objects.filter(
            harvest_date__year=current_year,
            harvest_date__month=month
        ).aggregate(total=Sum('quantity_tons'))['total'] or 0
        
        harvest_trends.append({
            'month': datetime(current_year, month, 1).strftime('%b'),
            'value': float(month_total)
        })
    
    # Get Crop Distribution data (for donut chart)
    crop_distribution = []
    total_crop_harvests = HarvestRecord.objects.aggregate(
        total=Sum('quantity_tons')
    )['total'] or 1
    
    crop_stats = HarvestRecord.objects.values('field__crop__name').annotate(
        total_quantity=Sum('quantity_tons')
    ).order_by('-total_quantity')
    
    for crop in crop_stats:
        percentage = (crop['total_quantity'] / total_crop_harvests) * 100
        crop_distribution.append({
            'crop': crop['field__crop__name'],
            'percentage': round(percentage, 1),
            'quantity': float(crop['total_quantity'])
        })
    
    # If no crop data, provide sample data to match Figma
    if not crop_distribution:
        crop_distribution = [
            {'crop': 'corn', 'percentage': 45.0, 'quantity': 0},
            {'crop': 'wheat', 'percentage': 30.0, 'quantity': 0},
            {'crop': 'soybeans', 'percentage': 25.0, 'quantity': 0}
        ]
    
    # Get Yield Performance data (for the new bar chart)
    yield_performance = []
    farms = Farm.objects.filter(is_active=True)[:4]  # Get first 4 farms
    
    if farms.exists():
        for i, farm in enumerate(farms):
            # Calculate expected yield based on total field area for this farm
            farm_fields = Field.objects.filter(farm=farm)
            total_area = farm_fields.aggregate(total=Sum('area_hectares'))['total'] or 0
            expected_yield = total_area * 5  # Assuming 5 tons per hectare baseline
            
            # Calculate actual yield from harvest records
            actual_yield = HarvestRecord.objects.filter(
                field__farm=farm
            ).aggregate(total=Sum('quantity_tons'))['total'] or 0
            
            yield_performance.append({
                'farm': f'Farm {chr(65 + i)}',  # Farm A, Farm B, etc.
                'expected': float(expected_yield),
                'actual': float(actual_yield)
            })
    else:
        # Sample data if no farms exist (matches Figma design)
        yield_performance = [
            {'farm': 'Farm A', 'expected': 2400, 'actual': 2500},
            {'farm': 'Farm B', 'expected': 1800, 'actual': 1600},
            {'farm': 'Farm C', 'expected': 2000, 'actual': 2100},
            {'farm': 'Farm D', 'expected': 1700, 'actual': 1750}
        ]
    
    # Get Recent Harvests (last 5 records)
    recent_harvests = HarvestRecord.objects.select_related(
        'field__farm', 'field__crop', 'harvested_by'
    ).order_by('-harvest_date')[:5]
    
    # Get Upcoming Harvests (fields with expected harvest dates in next 30 days)
    upcoming_date = datetime.now().date() + timedelta(days=30)
    upcoming_harvests = Field.objects.filter(
        expected_harvest_date__lte=upcoming_date,
        expected_harvest_date__gte=datetime.now().date()
    ).select_related('farm', 'crop').order_by('expected_harvest_date')[:5]
    
    # Calculate percentage changes (for the +12% indicators)
    last_month = datetime.now() - timedelta(days=30)
    last_month_harvests = HarvestRecord.objects.filter(
        harvest_date__gte=last_month
    ).aggregate(total=Sum('quantity_tons'))['total'] or 0
    
    context = {
        # Main dashboard metrics
        'total_harvested': total_harvested,
        'active_farms': active_farms,
        'total_inventory': total_inventory,
        'avg_yield_efficiency': avg_yield_efficiency,
        
        # Chart data (JSON serialized for JavaScript)
        'harvest_trends': json.dumps(harvest_trends),
        'crop_distribution': crop_distribution,
        'yield_performance': json.dumps(yield_performance),
        
        # Recent data
        'recent_harvests': recent_harvests,
        'upcoming_harvests': upcoming_harvests,
        
        # User info
        'user_role': request.user.userprofile.get_role_display() if hasattr(request.user, 'userprofile') else 'Demo User - Admin'
    }
    
    return render(request, 'monitoring/dashboard.html', context)

def farm_management(request):
    farms = Farm.objects.filter(is_active=True).prefetch_related('field_set__crop')

    # Calculate farm statistics
    total_farms = farms.count()
    active_farms = farms.filter(is_active=True).count()
    
    # Calculate totals
    total_area = Decimal('0')
    total_fields = 0
    total_harvested_all = Decimal('0')
    
    for farm in farms:
        # Total number of fields in the farm
        farm.field_count = farm.field_set.count()
        total_fields += farm.field_count

        # Total area of all fields in the farm (convert hectares to acres)
        farm_area = farm.field_set.aggregate(
            total=Sum('area_hectares')
        )['total'] or Decimal('0')
        farm.total_area = farm_area * Decimal('2.47105')  # Convert hectares to acres
        total_area += farm.total_area

        # Total harvested in this farm
        farm.total_harvested = HarvestRecord.objects.filter(
            field__farm=farm
        ).aggregate(total=Sum('quantity_tons'))['total'] or Decimal('0')
        total_harvested_all += farm.total_harvested

        # Calculate average yield for this farm
        if farm.total_area > 0:
            farm.avg_yield = farm.total_harvested / farm.total_area
        else:
            farm.avg_yield = Decimal('0')

    # Calculate average farm size
    avg_farm_size = total_area / total_farms if total_farms > 0 else Decimal('0')

    # Get recent farms (last 5 added)
    recent_farms = Farm.objects.order_by('-created_at')[:5] if hasattr(Farm, 'created_at') else farms[:5]

    # Get top performing farms (by average yield)
    top_farms = sorted(farms, key=lambda x: x.avg_yield, reverse=True)[:5]

    # Location distribution for chart
    location_distribution = []
    location_counts = defaultdict(int)
    for farm in farms:
        location = getattr(farm, 'location', 'Unknown')
        location_counts[location] += 1
    
    for location, count in location_counts.items():
        location_distribution.append({
            'location': location,
            'count': count
        })

    # Farm size distribution for chart
    size_distribution = []
    size_ranges = {
        '0-50 acres': 0,
        '51-100 acres': 0,
        '101-200 acres': 0,
        '200+ acres': 0
    }
    
    for farm in farms:
        size = farm.total_area
        if size <= 50:
            size_ranges['0-50 acres'] += 1
        elif size <= 100:
            size_ranges['51-100 acres'] += 1
        elif size <= 200:
            size_ranges['101-200 acres'] += 1
        else:
            size_ranges['200+ acres'] += 1
    
    for range_name, count in size_ranges.items():
        if count > 0:  # Only include ranges with farms
            size_distribution.append({
                'range': range_name,
                'count': count
            })

    context = {
        'total_farms': total_farms,
        'active_farms': active_farms,
        'total_area': round(float(total_area), 1),
        'avg_farm_size': round(float(avg_farm_size), 1),
        'total_fields': total_fields,
        'farms': farms,
        'recent_farms': recent_farms,
        'top_farms': top_farms,
        'location_distribution': location_distribution,
        'size_distribution': size_distribution,
    }

    return render(request, 'monitoring/farm_management.html', context)

def harvest_tracking(request):
    """
    Harvest Tracking view - shows recent harvests with filtering options
    """
    harvests = HarvestRecord.objects.select_related(
        'field__farm', 'field__crop', 'harvested_by'
    ).order_by('-harvest_date')[:50]
    
    # Get summary statistics
    total_harvests = HarvestRecord.objects.count()
    total_quantity = HarvestRecord.objects.aggregate(
        total=Sum('quantity_tons')
    )['total'] or 0
    
    # Get recent activity (last 7 days)
    week_ago = datetime.now().date() - timedelta(days=7)
    recent_activity = HarvestRecord.objects.filter(
        harvest_date__gte=week_ago
    ).count()
    
    context = {
        'harvests': harvests,
        'total_harvests': total_harvests,
        'total_quantity': total_quantity,
        'recent_activity': recent_activity
    }
    
    return render(request, 'monitoring/harvest_tracking.html', context)


@login_required
def analytics(request):
    """
    Analytics view - detailed charts and analysis
    """
    # Monthly trends for current year
    current_year = datetime.now().year
    monthly_data = []
    
    for month in range(1, 13):
        month_harvests = HarvestRecord.objects.filter(
            harvest_date__year=current_year,
            harvest_date__month=month
        )
        
        monthly_data.append({
            'month': datetime(current_year, month, 1).strftime('%B'),
            'harvest_count': month_harvests.count(),
            'total_quantity': month_harvests.aggregate(
                total=Sum('quantity_tons')
            )['total'] or 0
        })
    
    # Top performing farms
    top_farms = Farm.objects.annotate(
        total_harvest=Sum('field__harvestrecord__quantity_tons')
    ).order_by('-total_harvest')[:5]
    
    context = {
        'monthly_data': json.dumps(monthly_data),
        'top_farms': top_farms,
        'current_year': current_year
    }
    
    return render(request, 'monitoring/analytics.html', context)


@login_required
def inventory(request):
    """
    Inventory management view
    """
    inventory_items = Inventory.objects.select_related('crop').order_by('-updated_at')
    
    # Calculate total inventory value and quantity
    total_quantity = inventory_items.aggregate(
        total=Sum('quantity_tons')
    )['total'] or 0
    
    # Group by crop type
    crop_inventory = inventory_items.values('crop__name').annotate(
        total_quantity=Sum('quantity_tons'),
        item_count=Count('id')
    ).order_by('-total_quantity')
    
    context = {
        'inventory_items': inventory_items,
        'total_quantity': total_quantity,
        'crop_inventory': crop_inventory,
        'total_items': inventory_items.count()
    }
    
    return render(request, 'monitoring/inventory.html', context)


@login_required
def reports(request):
    """
    Reports view - generate various reports
    """
    # Generate summary statistics for reports
    current_month = datetime.now().replace(day=1)
    last_month = (current_month - timedelta(days=1)).replace(day=1)
    
    current_month_harvests = HarvestRecord.objects.filter(
        harvest_date__gte=current_month
    ).aggregate(
        count=Count('id'),
        total=Sum('quantity_tons')
    )
    
    last_month_harvests = HarvestRecord.objects.filter(
        harvest_date__gte=last_month,
        harvest_date__lt=current_month
    ).aggregate(
        count=Count('id'),
        total=Sum('quantity_tons')
    )
    
    context = {
        'current_month_data': current_month_harvests,
        'last_month_data': last_month_harvests,
        'current_month_name': current_month.strftime('%B %Y'),
        'last_month_name': last_month.strftime('%B %Y')
    }
    
    return render(request, 'monitoring/reports.html', context)


@login_required
def notifications(request):
    """
    Notifications view - show system notifications
    """
    # Get fields that need attention (harvest dates approaching)
    upcoming_harvests = Field.objects.filter(
        expected_harvest_date__lte=datetime.now().date() + timedelta(days=7),
        expected_harvest_date__gte=datetime.now().date()
    ).select_related('farm', 'crop')
    
    # Get low inventory alerts
    low_inventory = Inventory.objects.filter(
        quantity_tons__lt=100  # Alert when inventory is below 100 tons
    ).select_related('crop')
    
    context = {
        'upcoming_harvests': upcoming_harvests,
        'low_inventory': low_inventory,
        'notification_count': upcoming_harvests.count() + low_inventory.count()
    }
    
    return render(request, 'monitoring/notifications.html', context)


@login_required
def user_management(request):
    """
    User management view - only for admins and farm managers
    """
    # Check user permissions
    if hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['admin', 'farm_manager']:
        from django.contrib.auth.models import User
        
        users = User.objects.select_related('userprofile').order_by('username')
        
        # Get user statistics
        total_users = users.count()
        active_users = users.filter(is_active=True).count()
        
        context = {
            'users': users,
            'total_users': total_users,
            'active_users': active_users,
            'can_manage_users': True
        }
        
        return render(request, 'monitoring/user_management.html', context)
    else:
        return render(request, 'monitoring/access_denied.html', {
            'message': 'You do not have permission to access user management.'
        })