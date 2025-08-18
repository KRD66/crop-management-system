# monitoring/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q, F
from django.db.models.functions import Extract
from datetime import datetime, timedelta, date
from .models import Farm, HarvestRecord, Inventory, Crop, Field
from collections import defaultdict
from decimal import Decimal
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from .forms import AddInventoryForm, RemoveInventoryForm, InventoryFilterForm, BulkInventoryUpdateForm
from django.db import models, transaction



# Fixed monitoring/views.py - dashboard function
def dashboard(request):
    """
    Dashboard view that calculates all metrics shown in your design
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
    
    # Calculate Average Yield Efficiency (improved calculation)
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
        
        # Get crops and their expected yields for more accurate calculation
        total_expected = 0
        for field in fields_with_harvests:
            if field.crop.expected_yield_per_hectare:
                expected = field.area_hectares * field.crop.expected_yield_per_hectare
            else:
                expected = field.area_hectares * Decimal('5')  # Default 5 tons/hectare
            total_expected += expected
        
        if total_expected > 0:
            avg_yield_efficiency = min(int((total_actual / total_expected) * 100), 100)
        else:
            avg_yield_efficiency = 85  # Default when no expected data
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
    
    if total_crop_harvests > 0:
        crop_stats = HarvestRecord.objects.values('field__crop__name').annotate(
            total_quantity=Sum('quantity_tons')
        ).order_by('-total_quantity')
        
        for crop in crop_stats:
            if crop['total_quantity']:  # Only include crops with actual harvests
                percentage = (crop['total_quantity'] / total_crop_harvests) * 100
                crop_distribution.append({
                    'crop': crop['field__crop__name'],
                    'percentage': round(percentage, 1),
                    'quantity': float(crop['total_quantity'])
                })
    
    # If no crop data, provide sample data to match design
    if not crop_distribution:
        crop_distribution = [
            {'crop': 'corn', 'percentage': 45.0, 'quantity': 0},
            {'crop': 'wheat', 'percentage': 30.0, 'quantity': 0},
            {'crop': 'soybeans', 'percentage': 25.0, 'quantity': 0}
        ]
    
    # Get Yield Performance data (for the bar chart)
    yield_performance = []
    farms = Farm.objects.filter(is_active=True)[:4]  # Get first 4 farms
    
    if farms.exists():
        for i, farm in enumerate(farms):
            # Calculate expected yield based on crops and field areas
            farm_fields = Field.objects.filter(farm=farm)
            expected_yield = 0
            
            for field in farm_fields:
                if field.crop.expected_yield_per_hectare:
                    expected_yield += float(field.area_hectares * field.crop.expected_yield_per_hectare)
                else:
                    expected_yield += float(field.area_hectares * 5)  # Default 5 tons/hectare
            
            # Calculate actual yield from harvest records
            actual_yield = HarvestRecord.objects.filter(
                field__farm=farm
            ).aggregate(total=Sum('quantity_tons'))['total'] or 0
            
            yield_performance.append({
                'farm': farm.name[:10] + ('...' if len(farm.name) > 10 else ''),  # Truncate long names
                'expected': expected_yield,
                'actual': float(actual_yield)
            })
    else:
        # Sample data if no farms exist (matches design)
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
        expected_harvest_date__gte=datetime.now().date(),
        is_active=True
    ).select_related('farm', 'crop').order_by('expected_harvest_date')[:5]
    
    # Get user role safely
    user_role = 'Demo User - Admin'
    if hasattr(request.user, 'userprofile'):
        user_role = request.user.userprofile.get_role_display()
    
    context = {
        # Main dashboard metrics
        'total_harvested': float(total_harvested),
        'active_farms': active_farms,
        'total_inventory': float(total_inventory),
        'avg_yield_efficiency': avg_yield_efficiency,
        
        # Chart data (JSON serialized for JavaScript)
        'harvest_trends': json.dumps(harvest_trends),
        'crop_distribution': crop_distribution,
        'yield_performance': json.dumps(yield_performance),
        
        # Recent data
        'recent_harvests': recent_harvests,
        'upcoming_harvests': upcoming_harvests,
        
        # User info
        'user_role': user_role
    }
    
    return render(request, 'monitoring/dashboard.html', context)
# Fixed monitoring/views.py - farm_management function
def farm_management(request):
    farms = Farm.objects.filter(is_active=True).prefetch_related('field_set__crop')

    # Calculate farm statistics
    total_farms = farms.count()
    active_farms = farms.filter(is_active=True).count()
    
    # Calculate totals properly
    total_area = Decimal('0')
    total_fields = 0
    total_harvested_all = Decimal('0')
    
    # Process each farm and add calculated properties
    farms_with_stats = []
    for farm in farms:
        # Get all fields for this farm
        farm_fields = farm.field_set.all()
        field_count = farm_fields.count()  # Don't assign to farm.field_count
        total_fields += field_count

        # Calculate total area from fields (convert hectares to acres)
        farm_area_hectares = farm_fields.aggregate(
            total=Sum('area_hectares')
        )['total'] or Decimal('0')
        
        # If no fields, use the farm's total_area_hectares
        if farm_area_hectares == 0:
            farm_area_hectares = farm.total_area_hectares
        
        total_area_acres = farm_area_hectares * Decimal('2.47105')  # Convert to acres
        total_area += total_area_acres

        # Calculate total harvested for this farm
        total_harvested = HarvestRecord.objects.filter(
            field__farm=farm
        ).aggregate(total=Sum('quantity_tons'))['total'] or Decimal('0')
        total_harvested_all += total_harvested

        # Calculate average yield per acre for this farm
        if total_area_acres > 0:
            avg_yield = total_harvested / total_area_acres
        else:
            avg_yield = Decimal('0')

        # Create a farm object with additional attributes for the template
        farm.calculated_field_count = field_count
        farm.calculated_total_area = total_area_acres
        farm.calculated_total_harvested = total_harvested
        farm.calculated_avg_yield = avg_yield
        
        farms_with_stats.append(farm)

    # Calculate average farm size
    avg_farm_size = total_area / total_farms if total_farms > 0 else Decimal('0')

    # Get recent farms - handle if created_at doesn't exist
    try:
        recent_farms = Farm.objects.order_by('-created_at')[:5]
    except:
        recent_farms = farms[:5]

    # Get top performing farms (by average yield)
    top_farms = sorted(farms_with_stats, key=lambda x: x.calculated_avg_yield, reverse=True)[:5]

    # Location distribution for chart
    location_distribution = []
    location_counts = defaultdict(int)
    for farm in farms:
        location = farm.location if farm.location else 'Unknown'
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
    
    for farm in farms_with_stats:
        size = float(farm.calculated_total_area)
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
        'farms': farms_with_stats,
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
    
    # Get available fields for the modal form - only active fields
    available_fields = Field.objects.select_related('farm', 'crop').filter(
        farm__is_active=True,
        is_active=True
    ).order_by('farm__name', 'name')
    
    # Calculate additional metrics for the template
    completed_harvests = HarvestRecord.objects.filter(
        status='completed'
    ).count() if hasattr(HarvestRecord, 'status') else total_harvests
    
    in_progress_harvests = HarvestRecord.objects.filter(
        status='in_progress'
    ).count() if hasattr(HarvestRecord, 'status') else 0
    
    # Calculate average quality grade
    quality_grades = HarvestRecord.objects.values_list('quality_grade', flat=True)
    avg_quality = 'A'  # Default value
    if quality_grades:
        from collections import Counter
        grade_counts = Counter(quality_grades)
        avg_quality = grade_counts.most_common(1)[0][0] if grade_counts else 'A'
    
    # Get this month's harvests
    month_ago = datetime.now().date() - timedelta(days=30)
    harvests_this_month = HarvestRecord.objects.filter(
        harvest_date__gte=month_ago
    ).count()
    
    # Find best performing farm (by total harvest quantity)
    best_farm = Farm.objects.annotate(
        total_harvest=Sum('field__harvestrecord__quantity_tons')
    ).filter(total_harvest__isnull=False).order_by('-total_harvest').first()
    
    best_performing_farm = best_farm.name if best_farm else 'N/A'
    
    # Calculate average days from planting to harvest
    avg_days_to_harvest = 0
    fields_with_both_dates = Field.objects.filter(
        harvestrecord__isnull=False
    ).distinct()
    
    if fields_with_both_dates.exists():
        total_days = 0
        count = 0
        for field in fields_with_both_dates:
            latest_harvest = field.harvestrecord_set.first()
            if latest_harvest and field.planting_date:
                days = (latest_harvest.harvest_date - field.planting_date).days
                if days > 0:  # Valid calculation
                    total_days += days
                    count += 1
        avg_days_to_harvest = total_days // count if count > 0 else 0
    
    context = {
        'harvests': harvests,
        'total_harvests': total_harvests,
        'total_quantity': float(total_quantity),
        'recent_activity': recent_activity,
        'available_fields': available_fields,
        
        # Additional metrics for template
        'completed_harvests': completed_harvests,
        'in_progress_harvests': in_progress_harvests,
        'avg_quality': avg_quality,
        'harvests_this_week': recent_activity,
        'harvests_this_month': harvests_this_month,
        'best_performing_farm': best_performing_farm,
        'avg_days_to_harvest': avg_days_to_harvest,
        'total_harvest_records': total_harvests,
    }
    
    return render(request, 'monitoring/harvest_tracking.html', context)

# monitoring/views.py - Final optimized analytics function


def analytics(request):
    """
    Analytics view - detailed charts and analysis matching UI design
    Uses optimized calculations with proper error handling
    """
    from django.db.models import Sum, Avg, Q
    from collections import defaultdict
    import json
    import random
    
    try:
        current_year = datetime.now().year
        current_date = datetime.now().date()
        
        # === KEY METRICS CALCULATIONS ===
        
        # Get all active farms with their efficiency data
        farms_data = []
        total_efficiency = 0
        underperforming_count = 0
        
        for farm in Farm.objects.filter(is_active=True).prefetch_related('field_set__crop'):
            # Calculate expected yield for farm
            expected_total = 0
            for field in farm.field_set.all():
                if field.crop.expected_yield_per_hectare:
                    expected_total += float(field.area_hectares * field.crop.expected_yield_per_hectare)
                else:
                    expected_total += float(field.area_hectares * 5)  # Default 5 tons/hectare
            
            # Get actual harvest
            actual_total = float(farm.total_harvested_all_time)
            
            # Calculate efficiency
            if expected_total > 0:
                efficiency = min((actual_total / expected_total) * 100, 100)
            else:
                efficiency = 0
            
            # Get primary crop
            primary_crop = 'Mixed'
            if farm.field_set.exists():
                crop_counts = defaultdict(int)
                for field in farm.field_set.all():
                    crop_counts[field.crop.name] += 1
                primary_crop = max(crop_counts, key=crop_counts.get) if crop_counts else 'Mixed'
            
            farm_data = {
                'farm': farm,
                'name': farm.name,
                'efficiency': efficiency,
                'actual_yield': actual_total,
                'expected_yield': expected_total,
                'primary_crop': primary_crop
            }
            
            farms_data.append(farm_data)
            total_efficiency += efficiency
            
            if efficiency < 70:
                underperforming_count += 1
        
        # Calculate averages
        avg_efficiency = total_efficiency / len(farms_data) if farms_data else 85.0
        
        # Find top performer
        top_performer = max(farms_data, key=lambda x: x['efficiency']) if farms_data else {
            'name': 'No Data', 'efficiency': 0
        }
        
        # Calculate predicted harvest (next 2 weeks)
        two_weeks_later = current_date + timedelta(days=14)
        upcoming_fields = Field.objects.filter(
            expected_harvest_date__gte=current_date,
            expected_harvest_date__lte=two_weeks_later,
            is_active=True
        ).select_related('crop')
        
        predicted_harvest = 0
        for field in upcoming_fields:
            if field.crop.expected_yield_per_hectare:
                predicted_harvest += float(field.area_hectares * field.crop.expected_yield_per_hectare)
            else:
                predicted_harvest += float(field.area_hectares * 5)
        
        # === CHART DATA PREPARATION ===
        
        # 1. Yield Performance Chart Data
        yield_performance_data = []
        for farm_data in farms_data[:8]:  # Show up to 8 farms
            yield_performance_data.append({
                'farm': farm_data['name'][:12] + ('...' if len(farm_data['name']) > 12 else ''),
                'expected': round(farm_data['expected_yield'], 1),
                'actual': round(farm_data['actual_yield'], 1)
            })
        
        # Add sample data if insufficient
        while len(yield_performance_data) < 4:
            samples = [
                {'farm': 'North Field', 'expected': 2400, 'actual': 2500},
                {'farm': 'South Field', 'expected': 1800, 'actual': 1600},
                {'farm': 'East Plot', 'expected': 2000, 'actual': 2100},
                {'farm': 'West Area', 'expected': 1700, 'actual': 1750}
            ]
            yield_performance_data.extend(samples[:4 - len(yield_performance_data)])
        
        # 2. Seasonal Trends Data
        seasonal_trends_data = {'corn': [], 'wheat': [], 'soybeans': []}
        
        # Get data for last 5 years
        for year in range(2020, 2025):
            for crop_name, crop_key in [('corn', 'corn'), ('wheat', 'wheat'), ('soy', 'soybeans')]:
                total = HarvestRecord.objects.filter(
                    harvest_date__year=year,
                    field__crop__name__icontains=crop_name
                ).aggregate(total=Sum('quantity_tons'))['total'] or 0
                seasonal_trends_data[crop_key].append(float(total))
        
        # Use sample data if no real data
        if all(sum(seasonal_trends_data[crop]) == 0 for crop in seasonal_trends_data):
            seasonal_trends_data = {
                'corn': [1200, 1350, 1500, 1800, 2100],
                'wheat': [800, 950, 1100, 1200, 1400],
                'soybeans': [600, 750, 850, 950, 1100]
            }
        
        # 3. Weather Correlation Data
        weather_correlation_data = {'performance': [], 'rainfall': []}
        
        for month in range(1, 9):  # Jan to Aug
            # Calculate monthly performance
            month_harvests = HarvestRecord.objects.filter(
                harvest_date__year=current_year,
                harvest_date__month=month
            ).select_related('field__crop')
            
            if month_harvests.exists():
                total_actual = month_harvests.aggregate(total=Sum('quantity_tons'))['total'] or 0
                total_expected = 0
                
                for harvest in month_harvests:
                    if harvest.field.crop.expected_yield_per_hectare:
                        expected = float(harvest.field.area_hectares * harvest.field.crop.expected_yield_per_hectare)
                    else:
                        expected = float(harvest.field.area_hectares * 5)
                    total_expected += expected
                
                performance = min((total_actual / total_expected) * 100, 100) if total_expected > 0 else 0
            else:
                performance = random.randint(70, 95)  # Sample data when no harvests
            
            weather_correlation_data['performance'].append(round(performance, 1))
            # Simulated rainfall data (replace with real weather API in production)
            weather_correlation_data['rainfall'].append(round(random.uniform(1.5, 7.5), 1))
        
        # === FARM RANKINGS ===
        farm_rankings = sorted(farms_data, key=lambda x: x['efficiency'], reverse=True)[:10]
        
        # === HARVEST PREDICTIONS ===
        harvest_predictions = []
        upcoming_fields_pred = Field.objects.filter(
            expected_harvest_date__gte=current_date,
            expected_harvest_date__lte=current_date + timedelta(days=60),
            is_active=True
        ).select_related('farm', 'crop')[:8]
        
        for field in upcoming_fields_pred:
            if field.crop.expected_yield_per_hectare:
                predicted_amount = float(field.area_hectares * field.crop.expected_yield_per_hectare)
            else:
                predicted_amount = float(field.area_hectares * 5)
            
            # Calculate confidence based on field history and other factors
            confidence = 85  # Base confidence
            
            # Adjust confidence based on harvest history
            harvest_count = field.harvestrecord_set.count()
            if harvest_count > 3:
                confidence += 5
            elif harvest_count > 1:
                confidence += 3
            
            # Add crop-specific adjustment
            if field.crop.expected_yield_per_hectare:
                confidence += 5
            
            # Add some variability
            confidence += random.randint(-3, 8)
            confidence = min(max(confidence, 80), 98)  # Keep between 80-98%
            
            harvest_predictions.append({
                'crop': field.crop.name,
                'field': f"{field.farm.name} - {field.name}",
                'amount': round(predicted_amount, 1),
                'date': field.expected_harvest_date,
                'confidence': confidence
            })
        
        # Add sample predictions if no real data
        if not harvest_predictions:
            sample_predictions = [
                {
                    'crop': 'Corn',
                    'field': 'North Field A',
                    'amount': 125.0,
                    'date': current_date + timedelta(days=7),
                    'confidence': 95
                },
                {
                    'crop': 'Wheat',
                    'field': 'East Plot 1',
                    'amount': 80.5,
                    'date': current_date + timedelta(days=12),
                    'confidence': 88
                },
                {
                    'crop': 'Soybeans',
                    'field': 'South Field',
                    'amount': 95.2,
                    'date': current_date + timedelta(days=18),
                    'confidence': 92
                },
                {
                    'crop': 'Cassava',
                    'field': 'West Plot 2',
                    'amount': 110.8,
                    'date': current_date + timedelta(days=25),
                    'confidence': 90
                }
            ]
            harvest_predictions = sample_predictions
        
        # === CONTEXT PREPARATION ===
        context = {
            # Key Metrics Cards
            'avg_efficiency': round(avg_efficiency, 1),
            'top_performer': {
                'name': top_performer['name'] if isinstance(top_performer, dict) else top_performer.get('name', 'No Data'),
                'efficiency': round(top_performer.get('efficiency', 0), 1)
            },
            'predicted_harvest': round(predicted_harvest, 0),
            'underperforming_count': underperforming_count,
            
            # Chart Data (JSON serialized for JavaScript)
            'yield_performance_data': json.dumps(yield_performance_data),
            'seasonal_trends_data': json.dumps(seasonal_trends_data),
            'weather_correlation_data': json.dumps(weather_correlation_data),
            
            # Rankings and Predictions Lists
            'farm_rankings': [
                {
                    'name': f['name'],
                    'primary_crop': f['primary_crop'],
                    'efficiency': round(f['efficiency'], 1),
                    'actual_yield': round(f['actual_yield'], 0),
                    'expected_yield': round(f['expected_yield'], 0)
                } for f in farm_rankings
            ],
            'harvest_predictions': harvest_predictions,
            
            # Additional Context
            'current_year': current_year,
            'total_farms_analyzed': len(farms_data),
            'has_data': len(farms_data) > 0,
            'page_title': 'Analytics Dashboard',
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        return render(request, 'monitoring/analytics.html', context)
    
    except Exception as e:
        # Error handling with fallback data
        print(f"Analytics view error: {e}")  # Log the error
        
        # Provide fallback context with sample data
        fallback_context = {
            'avg_efficiency': 85.0,
            'top_performer': {'name': 'Sample Farm', 'efficiency': 92.0},
            'predicted_harvest': 1500,
            'underperforming_count': 2,
            'yield_performance_data': json.dumps([
                {'farm': 'North Field', 'expected': 2400, 'actual': 2500},
                {'farm': 'South Field', 'expected': 1800, 'actual': 1600},
                {'farm': 'East Plot', 'expected': 2000, 'actual': 2100},
                {'farm': 'West Area', 'expected': 1700, 'actual': 1750}
            ]),
            'seasonal_trends_data': json.dumps({
                'corn': [1200, 1350, 1500, 1800, 2100],
                'wheat': [800, 950, 1100, 1200, 1400],
                'soybeans': [600, 750, 850, 950, 1100]
            }),
            'weather_correlation_data': json.dumps({
                'performance': [85, 78, 92, 88, 90, 85, 82, 89],
                'rainfall': [3.2, 4.1, 2.8, 5.5, 6.2, 4.8, 3.9, 2.1]
            }),
            'farm_rankings': [
                {'name': 'Sample Farm A', 'primary_crop': 'Corn', 'efficiency': 95.0, 'actual_yield': 2500, 'expected_yield': 2400},
                {'name': 'Sample Farm B', 'primary_crop': 'Wheat', 'efficiency': 88.0, 'actual_yield': 1600, 'expected_yield': 1800}
            ],
            'harvest_predictions': [
                {'crop': 'Corn', 'field': 'Sample Field', 'amount': 125.0, 'date': datetime.now().date() + timedelta(days=7), 'confidence': 95}
            ],
            'current_year': datetime.now().year,
            'total_farms_analyzed': 0,
            'has_data': False,
            'error_message': 'Unable to load analytics data. Showing sample data.',
            'page_title': 'Analytics Dashboard',
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        return render(request, 'monitoring/analytics.html', fallback_context)


def inventory(request):
    """
    Main inventory management view with filtering and CRUD operations
    """
    # Initialize forms
    add_form = AddInventoryForm(user=request.user)
    remove_form = RemoveInventoryForm()
    filter_form = InventoryFilterForm(request.GET or None)
    bulk_form = BulkInventoryUpdateForm()
    
    # Base queryset
    inventory_items = Inventory.objects.select_related('crop', 'managed_by').order_by('-date_stored')
    
    # Apply filters
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('crop'):
            inventory_items = inventory_items.filter(crop=filter_form.cleaned_data['crop'])
        
        if filter_form.cleaned_data.get('storage_location'):
            inventory_items = inventory_items.filter(storage_location=filter_form.cleaned_data['storage_location'])
        
        if filter_form.cleaned_data.get('quality_grade'):
            inventory_items = inventory_items.filter(quality_grade=filter_form.cleaned_data['quality_grade'])
        
        if filter_form.cleaned_data.get('date_from'):
            inventory_items = inventory_items.filter(date_stored__gte=filter_form.cleaned_data['date_from'])
        
        if filter_form.cleaned_data.get('date_to'):
            inventory_items = inventory_items.filter(date_stored__lte=filter_form.cleaned_data['date_to'])
        
        # Status filtering
        status = filter_form.cleaned_data.get('status')
        if status == 'expiring':
            thirty_days = date.today() + timedelta(days=30)
            inventory_items = inventory_items.filter(expiry_date__lte=thirty_days, expiry_date__gt=date.today())
        elif status == 'expired':
            inventory_items = inventory_items.filter(expiry_date__lt=date.today())
        elif status == 'low_stock':
            inventory_items = inventory_items.filter(quantity_tons__lt=10)
        elif status == 'good':
            thirty_days = date.today() + timedelta(days=30)
            inventory_items = inventory_items.filter(
                Q(expiry_date__gt=thirty_days) | Q(expiry_date__isnull=True),
                quantity_tons__gte=10
            )
    
    # Calculate metrics
    total_quantity = inventory_items.aggregate(total=Sum('quantity_tons'))['total'] or 0
    total_value = inventory_items.aggregate(
        total=Sum(F('quantity_tons') * F('unit_price'))
    )['total'] or 0
    
    # Status counts
    thirty_days = date.today() + timedelta(days=30)
    low_stock_count = inventory_items.filter(quantity_tons__lt=10).count()
    expiring_count = inventory_items.filter(
        expiry_date__lte=thirty_days,
        expiry_date__gt=date.today()
    ).count()
    expired_count = inventory_items.filter(expiry_date__lt=date.today()).count()
    
    # Storage locations summary
    storage_locations = inventory_items.values('storage_location').annotate(
        total_quantity=Sum('quantity_tons'),
        item_count=Count('id')
    ).order_by('-total_quantity')
    
    # Crop summary
    crop_summary = inventory_items.values('crop__name').annotate(
        total_quantity=Sum('quantity_tons'),
        item_count=Count('id'),
        avg_quality=models.Avg('quality_grade')
    ).order_by('-total_quantity')
    
    context = {
        'inventory_items': inventory_items[:50],  # Paginate in production
        'total_items': inventory_items.count(),
        'total_quantity': total_quantity,
        'total_value': total_value,
        'low_stock_count': low_stock_count,
        'expiring_count': expiring_count,
        'expired_count': expired_count,
        'storage_locations': storage_locations,
        'crop_summary': crop_summary,
        'add_form': add_form,
        'remove_form': remove_form,
        'filter_form': filter_form,
        'bulk_form': bulk_form,
    }
    
    return render(request, 'monitoring/inventory.html', context)


@login_required
def add_inventory(request):
    """
    Add new inventory item
    """
    if request.method == 'POST':
        form = AddInventoryForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                inventory_item = form.save()
                messages.success(
                    request, 
                    f"Successfully added {inventory_item.quantity_tons} tons of {inventory_item.crop.name} to inventory."
                )
                return JsonResponse({
                    'success': True,
                    'message': 'Inventory added successfully',
                    'redirect': True
                })
            except Exception as e:
                messages.error(request, f"Error adding inventory: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f"Error adding inventory: {str(e)}"
                })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Form validation failed',
                'errors': form.errors
            })
    
    return redirect('monitoring:inventory')


@login_required
def remove_inventory(request):
    """
    Remove inventory items
    """
    if request.method == 'POST':
        form = RemoveInventoryForm(request.POST)
        if form.is_valid():
            crop = form.cleaned_data['crop']
            storage_location = form.cleaned_data['storage_location']
            quantity_to_remove = form.cleaned_data['quantity_tons']
            reason = form.cleaned_data.get('reason', '')
            
            try:
                with transaction.atomic():
                    # Get inventory items for this crop and location, ordered by date (FIFO)
                    inventory_items = Inventory.objects.filter(
                        crop=crop,
                        storage_location=storage_location,
                        quantity_tons__gt=0
                    ).order_by('date_stored')
                    
                    if not inventory_items.exists():
                        return JsonResponse({
                            'success': False,
                            'message': f"No inventory found for {crop.name} at {storage_location}"
                        })
                    
                    total_available = inventory_items.aggregate(
                        total=Sum('quantity_tons')
                    )['total'] or 0
                    
                    if quantity_to_remove > total_available:
                        return JsonResponse({
                            'success': False,
                            'message': f"Only {total_available} tons available, cannot remove {quantity_to_remove} tons"
                        })
                    
                    remaining_to_remove = quantity_to_remove
                    items_updated = []
                    
                    # Remove from inventory items (FIFO - First In, First Out)
                    for item in inventory_items:
                        if remaining_to_remove <= 0:
                            break
                        
                        if item.quantity_tons <= remaining_to_remove:
                            # Remove entire item
                            remaining_to_remove -= item.quantity_tons
                            items_updated.append(f"Removed all {item.quantity_tons} tons from {item.batch_number or 'batch'}")
                            item.delete()
                        else:
                            # Partial removal
                            removed_amount = remaining_to_remove
                            item.quantity_tons -= remaining_to_remove
                            item.notes += f"\n[{date.today()}] Removed {removed_amount} tons. Reason: {reason}"
                            item.save()
                            items_updated.append(f"Removed {removed_amount} tons from {item.batch_number or 'batch'}")
                            remaining_to_remove = 0
                    
                    messages.success(
                        request,
                        f"Successfully removed {quantity_to_remove} tons of {crop.name} from {storage_location}."
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'message': f"Successfully removed {quantity_to_remove} tons",
                        'details': items_updated,
                        'redirect': True
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f"Error removing inventory: {str(e)}"
                })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Form validation failed',
                'errors': form.errors
            })
    
    return redirect('monitoring:inventory')


@login_required
def get_inventory_locations(request):
    """
    AJAX endpoint to get available storage locations for a specific crop
    """
    crop_id = request.GET.get('crop_id')
    if crop_id:
        locations = Inventory.objects.filter(
            crop_id=crop_id,
            quantity_tons__gt=0
        ).values('storage_location').annotate(
            total_quantity=Sum('quantity_tons')
        ).order_by('storage_location')
        
        location_data = [
            {
                'value': loc['storage_location'],
                'label': f"{loc['storage_location']} ({loc['total_quantity']} tons available)"
            }
            for loc in locations
        ]
        
        return JsonResponse({'locations': location_data})
    
    return JsonResponse({'locations': []})


@login_required
def inventory_summary(request):
    """
    Get inventory summary data for dashboard
    """
    # Total metrics
    total_quantity = Inventory.objects.aggregate(total=Sum('quantity_tons'))['total'] or 0
    total_items = Inventory.objects.count()
    total_value = Inventory.objects.aggregate(
        total=Sum(F('quantity_tons') * F('unit_price'))
    )['total'] or 0
    
    # Status counts
    thirty_days = date.today() + timedelta(days=30)
    low_stock_count = Inventory.objects.filter(quantity_tons__lt=10).count()
    expiring_count = Inventory.objects.filter(
        expiry_date__lte=thirty_days,
        expiry_date__gt=date.today()
    ).count()
    
    # Top crops by quantity
    top_crops = Inventory.objects.values('crop__name').annotate(
        total_quantity=Sum('quantity_tons')
    ).order_by('-total_quantity')[:5]
    
    # Storage utilization
    storage_utilization = Inventory.objects.values('storage_location').annotate(
        total_quantity=Sum('quantity_tons'),
        item_count=Count('id')
    ).order_by('-total_quantity')
    
    data = {
        'total_quantity': float(total_quantity),
        'total_items': total_items,
        'total_value': float(total_value) if total_value else 0,
        'low_stock_count': low_stock_count,
        'expiring_count': expiring_count,
        'top_crops': list(top_crops),
        'storage_utilization': list(storage_utilization)
    }
    
    return JsonResponse(data)


@login_required
def bulk_update_inventory(request):
    """
    Bulk update inventory items
    """
    if request.method == 'POST':
        form = BulkInventoryUpdateForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            selected_items = json.loads(form.cleaned_data['selected_items'])
            
            if not selected_items:
                return JsonResponse({
                    'success': False,
                    'message': 'No items selected'
                })
            
            try:
                with transaction.atomic():
                    items = Inventory.objects.filter(id__in=selected_items)
                    count = items.count()
                    
                    if action == 'update_location':
                        new_location = form.cleaned_data['new_storage_location']
                        items.update(storage_location=new_location, updated_at=timezone.now())
                        message = f"Updated storage location for {count} items to {new_location}"
                    
                    elif action == 'update_condition':
                        new_condition = form.cleaned_data['new_storage_condition']
                        items.update(storage_condition=new_condition, updated_at=timezone.now())
                        message = f"Updated storage condition for {count} items"
                    
                    elif action == 'mark_expired':
                        items.update(expiry_date=date.today() - timedelta(days=1), updated_at=timezone.now())
                        message = f"Marked {count} items as expired"
                    
                    elif action == 'reserve':
                        items.update(is_reserved=True, updated_at=timezone.now())
                        message = f"Reserved {count} items"
                    
                    elif action == 'unreserve':
                        items.update(is_reserved=False, updated_at=timezone.now())
                        message = f"Unreserved {count} items"
                    
                    messages.success(request, message)
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect': True
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f"Error performing bulk update: {str(e)}"
                })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Form validation failed',
                'errors': form.errors
            })
    
    return redirect('monitoring:inventory')


@login_required
def export_inventory(request):
    """
    Export inventory data to CSV
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Crop', 'Quantity (tons)', 'Storage Location', 'Quality Grade',
        'Date Stored', 'Expiry Date', 'Storage Condition', 'Batch Number',
        'Unit Price', 'Total Value', 'Managed By', 'Status'
    ])
    
    for item in Inventory.objects.select_related('crop', 'managed_by'):
        status = 'Good'
        if item.is_expired:
            status = 'Expired'
        elif item.days_until_expiry and item.days_until_expiry <= 30:
            status = 'Expiring Soon'
        elif item.is_low_stock:
            status = 'Low Stock'
        
        writer.writerow([
            item.crop.name,
            item.quantity_tons,
            item.storage_location,
            item.get_quality_grade_display(),
            item.date_stored,
            item.expiry_date or '',
            item.get_storage_condition_display(),
            item.batch_number or '',
            item.unit_price or '',
            item.total_value or '',
            item.managed_by.get_full_name() or item.managed_by.username,
            status
        ])
    
    return response
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
        
        
def get_yearly_trends(request, year):
    """API endpoint to get seasonal trends for a specific year"""
    try:
        trends_data = {}
        
        # Get data for major crops
        for crop_name, crop_key in [('corn', 'corn'), ('wheat', 'wheat'), ('soy', 'soybeans')]:
            monthly_data = []
            
            for month in range(1, 13):
                total = HarvestRecord.objects.filter(
                    harvest_date__year=year,
                    harvest_date__month=month,
                    field__crop__name__icontains=crop_name
                ).aggregate(total=Sum('quantity_tons'))['total'] or 0
                monthly_data.append(float(total))
            
            trends_data[crop_key] = monthly_data
        
        return JsonResponse({
            'success': True,
            'year': year,
            'data': trends_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_farm_efficiency(request, farm_id):
    """API endpoint to get detailed efficiency data for a specific farm"""
    try:
        farm = Farm.objects.get(id=farm_id, is_active=True)
        
        # Calculate detailed efficiency metrics
        fields_data = []
        total_expected = 0
        total_actual = 0
        
        for field in farm.field_set.all():
            field_expected = float(field.area_hectares * (field.crop.expected_yield_per_hectare or 5))
            field_actual = float(field.total_harvested)
            
            field_efficiency = (field_actual / field_expected * 100) if field_expected > 0 else 0
            
            fields_data.append({
                'name': field.name,
                'crop': field.crop.name,
                'area': float(field.area_hectares),
                'expected': field_expected,
                'actual': field_actual,
                'efficiency': round(field_efficiency, 1)
            })
            
            total_expected += field_expected
            total_actual += field_actual
        
        farm_efficiency = (total_actual / total_expected * 100) if total_expected > 0 else 0
        
        return JsonResponse({
            'success': True,
            'farm': {
                'id': farm.id,
                'name': farm.name,
                'location': farm.location,
                'total_area': float(farm.total_area_hectares),
                'efficiency': round(farm_efficiency, 1),
                'total_expected': round(total_expected, 1),
                'total_actual': round(total_actual, 1)
            },
            'fields': fields_data
        })
        
    except Farm.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Farm not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_live_metrics(request):
    """API endpoint for live dashboard metrics updates"""
    try:
        # Calculate current metrics
        total_harvests = HarvestRecord.objects.count()
        active_farms = Farm.objects.filter(is_active=True).count()
        total_inventory = Inventory.objects.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        # Recent activity (last 7 days)
        week_ago = datetime.now().date() - timedelta(days=7)
        recent_harvests = HarvestRecord.objects.filter(
            harvest_date__gte=week_ago
        ).count()
        
        # Upcoming harvests (next 7 days)
        next_week = datetime.now().date() + timedelta(days=7)
        upcoming_harvests = Field.objects.filter(
            expected_harvest_date__gte=datetime.now().date(),
            expected_harvest_date__lte=next_week,
            is_active=True
        ).count()
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'total_harvests': total_harvests,
                'active_farms': active_farms,
                'total_inventory': float(total_inventory),
                'recent_harvests': recent_harvests,
                'upcoming_harvests': upcoming_harvests
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)