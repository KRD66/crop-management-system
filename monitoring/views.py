# monitoring/views.py - Integrated views with user management and farm monitoring
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg, F
from django.db.models.functions import Extract
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction, models
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
from collections import defaultdict
import json
import csv
import random
from io import BytesIO
from .forms import UserAddForm, FarmForm,HarvestForm
from django.db.models import Sum
from .models import Farm, HarvestRecord


# ReportLab imports for PDF generation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# OpenPyXL imports for Excel generation
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# Import models
from .models import (
    Farm, HarvestRecord, Inventory, Crop, Field, UserProfile
)

# Import forms
from .forms import (
    AdminUserCreationForm, UserProfileUpdateForm, PasswordResetRequestForm,
    AddInventoryForm, RemoveInventoryForm, InventoryFilterForm, BulkInventoryUpdateForm
)

# Import custom decorators
from .auth_views import admin_added_required, role_required


# ========================
# DASHBOARD AND MAIN VIEWS
# ========================

@login_required
@admin_added_required
def dashboard(request):
    """
    Main dashboard view that calculates all metrics shown in the design
    """
    try:
        # Calculate Total Harvested
        total_harvested = HarvestRecord.objects.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        # Calculate Active Farms
        active_farms = Farm.objects.filter(is_active=True).count()
        
        # Calculate Total Inventory
        total_inventory = Inventory.objects.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        # Calculate Average Yield Efficiency
        fields_with_harvests = Field.objects.filter(
            harvestrecord__isnull=False
        ).distinct()
        
        if fields_with_harvests.exists():
            total_actual = HarvestRecord.objects.aggregate(
                total=Sum('quantity_tons')
            )['total'] or 0
            
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
                avg_yield_efficiency = 85
        else:
            avg_yield_efficiency = 85
        
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
                if crop['total_quantity']:
                    percentage = (crop['total_quantity'] / total_crop_harvests) * 100
                    crop_distribution.append({
                        'crop': crop['field__crop__name'],
                        'percentage': round(percentage, 1),
                        'quantity': float(crop['total_quantity'])
                    })
        
        # If no crop data, provide sample data
        if not crop_distribution:
            crop_distribution = [
                {'crop': 'corn', 'percentage': 45.0, 'quantity': 0},
                {'crop': 'wheat', 'percentage': 30.0, 'quantity': 0},
                {'crop': 'soybeans', 'percentage': 25.0, 'quantity': 0}
            ]
        
        # Get Yield Performance data (for the bar chart)
        yield_performance = []
        farms = Farm.objects.filter(is_active=True)[:4]
        
        if farms.exists():
            for farm in farms:
                farm_fields = Field.objects.filter(farm=farm)
                expected_yield = 0
                
                for field in farm_fields:
                    if field.crop.expected_yield_per_hectare:
                        expected_yield += float(field.area_hectares * field.crop.expected_yield_per_hectare)
                    else:
                        expected_yield += float(field.area_hectares * 5)
                
                actual_yield = HarvestRecord.objects.filter(
                    field__farm=farm
                ).aggregate(total=Sum('quantity_tons'))['total'] or 0
                
                yield_performance.append({
                    'farm': farm.name[:10] + ('...' if len(farm.name) > 10 else ''),
                    'expected': expected_yield,
                    'actual': float(actual_yield)
                })
        else:
            # Sample data if no farms exist
            yield_performance = [
                {'farm': 'Farm A', 'expected': 2400, 'actual': 2500},
                {'farm': 'Farm B', 'expected': 1800, 'actual': 1600},
                {'farm': 'Farm C', 'expected': 2000, 'actual': 2100},
                {'farm': 'Farm D', 'expected': 1700, 'actual': 1750}
            ]
        
        # Get Recent Harvests
        recent_harvests = HarvestRecord.objects.select_related(
            'field__farm', 'field__crop', 'harvested_by'
        ).order_by('-harvest_date')[:5]
        
        # Get Upcoming Harvests
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
            'user_role': user_role,
            'user_profile': getattr(request.user, 'userprofile', None)
        }
        
        return render(request, 'monitoring/dashboard.html', context)
        
    except Exception as e:
        print(f"Dashboard error: {e}")
        # Return basic context on error
        context = {
            'total_harvested': 0,
            'active_farms': 0,
            'total_inventory': 0,
            'avg_yield_efficiency': 85,
            'harvest_trends': json.dumps([]),
            'crop_distribution': [],
            'yield_performance': json.dumps([]),
            'recent_harvests': [],
            'upcoming_harvests': [],
            'user_role': 'User',
            'error_message': 'Unable to load dashboard data'
        }
        return render(request, 'monitoring/dashboard.html', context)


# ========================
# USER MANAGEMENT VIEWS
# ========================
@role_required(['admin'])
@login_required
def user_management(request):
    """User management view - Admin only"""
    search_query = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    
    users = User.objects.select_related('userprofile').all()
    
    # Apply filters
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    if role_filter:
        users = users.filter(userprofile__role=role_filter)
    
    if status_filter == 'active':
        users = users.filter(userprofile__is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(userprofile__is_active=False)
    
    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    stats = {
        'total_users': User.objects.filter(userprofile__isnull=False).count(),
        'active_users': UserProfile.objects.filter(is_active=True).count(),
        'inactive_users': UserProfile.objects.filter(is_active=False).count(),
        'admin_users': UserProfile.objects.filter(role='admin').count(),
    }
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'role_choices': UserProfile.ROLE_CHOICES if hasattr(UserProfile, 'ROLE_CHOICES') else [],
        'stats': stats,
        'can_manage_users': True
    }
    
    return render(request, 'monitoring/user_management.html', context)



@login_required
@role_required(['admin'])
def user_edit(request, user_id):
    """Edit user - Admin only"""
    user = get_object_or_404(User, id=user_id)
    
    if user.is_superuser and not request.user.is_superuser:
        messages.error(request, 'You cannot edit superuser accounts.')
        return redirect('monitoring:user_management')
    
    if request.method == 'POST':
        form = UserProfileUpdateForm(request.POST, instance=user.userprofile, user=user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'User {user.username} updated successfully.')
                return redirect('monitoring:user_management')
            except Exception as e:
                messages.error(request, f'Error updating user: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.title()}: {error}')
    else:
        form = UserProfileUpdateForm(instance=user.userprofile, user=user)
    
    context = {
        'form': form,
        'user': user,
        'title': f'Edit User: {user.username}',
        'submit_text': 'Update User'
    }
    return render(request, 'monitoring/user_form.html', context)


@login_required
@role_required(['admin'])
@require_http_methods(["POST"])
def user_deactivate(request, user_id):
    """Deactivate user - Admin only"""
    user = get_object_or_404(User, id=user_id)
    
    if user.is_superuser and not request.user.is_superuser:
        messages.error(request, 'You cannot deactivate superuser accounts.')
        return redirect('monitoring:user_management')
    
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('monitoring:user_management')
    
    try:
        user.userprofile.is_active = False
        user.userprofile.save()
        user.is_active = False
        user.save()
        
        messages.success(request, f'User {user.username} has been deactivated.')
    except Exception as e:
        messages.error(request, f'Error deactivating user: {str(e)}')
    
    return redirect('monitoring:user_management')


@login_required
@role_required(['admin'])
@require_http_methods(["POST"])
def user_activate(request, user_id):
    """Activate user - Admin only"""
    user = get_object_or_404(User, id=user_id)
    
    try:
        user.userprofile.is_active = True
        user.userprofile.save()
        user.is_active = True
        user.save()
        
        messages.success(request, f'User {user.username} has been activated.')
    except Exception as e:
        messages.error(request, f'Error activating user: {str(e)}')
    
    return redirect('monitoring:user_management')


@login_required
@role_required(['admin'])
@require_http_methods(["POST"])
def user_delete(request, user_id):
    """Delete user - Admin only"""
    user = get_object_or_404(User, id=user_id)
    
    if user.is_superuser and not request.user.is_superuser:
        messages.error(request, 'You cannot delete superuser accounts.')
        return redirect('monitoring:user_management')
    
    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('monitoring:user_management')
    
    try:
        username = user.username
        user.delete()
        messages.success(request, f'User {username} has been deleted.')
    except Exception as e:
        messages.error(request, f'Error deleting user: {str(e)}')
    
    return redirect('monitoring:user_management')


@login_required
@role_required(['admin'])
def user_reset_password(request, user_id):
    """Reset user password - Admin only"""
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not new_password or len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        elif new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        else:
            try:
                user.set_password(new_password)
                user.save()
                messages.success(
                    request, 
                    f'Password for user {user.username} has been reset successfully.'
                )
                return redirect('monitoring:user_management')
            except Exception as e:
                messages.error(request, f'Error resetting password: {str(e)}')
    
    context = {
        'user': user,
        'title': f'Reset Password for: {user.username}',
    }
    return render(request, 'monitoring/user_reset_password.html', context)

@login_required
@admin_added_required
def profile_view(request):
    """View user profile"""
    context = {
        'user': request.user,
        'profile': request.user.userprofile,
    }
    return render(request, 'monitoring/profile.html', context)


@login_required
@admin_added_required
def profile_edit(request):
    """Edit user profile (limited fields)"""
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        
        try:
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.save()
            
            request.user.userprofile.phone_number = phone_number
            request.user.userprofile.save()
            
            messages.success(request, 'Profile updated successfully.')
            return redirect('monitoring:profile')
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')
    
    context = {
        'user': request.user,
        'profile': request.user.userprofile,
    }
    return render(request, 'monitoring/profile_edit.html', context)


def password_reset_request(request):
    """Password reset request form"""
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            reason = form.cleaned_data.get('reason', '')
            
            messages.success(
                request,
                'Password reset request submitted successfully. '
                'An administrator will contact you soon to reset your password.'
            )
            return redirect('monitoring:login')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.title()}: {error}')
    else:
        form = PasswordResetRequestForm()
    
    context = {
        'form': form,
        'title': 'Request Password Reset',
    }
    return render(request, 'monitoring/password_reset_request.html', context)


# ========================
# FARM MANAGEMENT VIEWS
# ========================


@login_required
@admin_added_required  # Keep your existing decorator
def farm_management(request):
    """Farm management view - your existing comprehensive view"""
    # Add form for the modal
    form = FarmForm()
    
    farms = Farm.objects.filter(is_active=True).prefetch_related('field_set__crop')

    total_farms = farms.count()
    active_farms = farms.filter(is_active=True).count()
    
    total_area = Decimal('0')
    total_fields = 0
    total_harvested_all = Decimal('0')
    
    farms_with_stats = []
    for farm in farms:
        farm_fields = farm.field_set.all()
        field_count = farm_fields.count()
        total_fields += field_count

        farm_area_hectares = farm_fields.aggregate(
            total=Sum('area_hectares')
        )['total'] or Decimal('0')
        
        if farm_area_hectares == 0:
            farm_area_hectares = farm.total_area_hectares
        
        total_area_acres = farm_area_hectares * Decimal('2.47105')  # Convert to acres
        total_area += total_area_acres

        total_harvested = HarvestRecord.objects.filter(
            field__farm=farm
        ).aggregate(total=Sum('quantity_tons'))['total'] or Decimal('0')
        total_harvested_all += total_harvested

        if total_area_acres > 0:
            avg_yield = total_harvested / total_area_acres
        else:
            avg_yield = Decimal('0')

        farm.calculated_field_count = field_count
        farm.calculated_total_area = total_area_acres
        farm.calculated_total_harvested = total_harvested
        farm.calculated_avg_yield = avg_yield
        
        farms_with_stats.append(farm)

    avg_farm_size = total_area / total_farms if total_farms > 0 else Decimal('0')

    try:
        recent_farms = Farm.objects.order_by('-created_at')[:5]
    except:
        recent_farms = farms[:5]

    top_farms = sorted(farms_with_stats, key=lambda x: x.calculated_avg_yield, reverse=True)[:5]

    # Location distribution
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

    # Size distribution
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
        if count > 0:
            size_distribution.append({
                'range': range_name,
                'count': count
            })

    context = {
        'form': form,  # Add the form for the modal
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

@login_required
@require_http_methods(["POST"])  # Only accept POST requests
def farm_add(request):
    """Handle adding a new farm via modal form submission"""
    form = FarmForm(request.POST)
    
    if form.is_valid():
        try:
            farm = form.save(commit=False)
            farm.manager = request.user
            farm.is_active = True  # Set as active by default
            farm.save()
            
            # Handle crop types from checkboxes if needed
            crop_types = request.POST.getlist('crop_types')
            if crop_types:
                # Add crop types to notes or handle them as needed
                if farm.notes:
                    farm.notes += f"\nCrops: {', '.join(crop_types)}"
                else:
                    farm.notes = f"Crops: {', '.join(crop_types)}"
                farm.save()
            
            messages.success(request, f"Farm '{farm.name}' added successfully!")
            
        except Exception as e:
            messages.error(request, f"Error adding farm: {str(e)}")
    else:
        # Form has validation errors
        for field, errors in form.errors.items():
            for error in errors:
                if field == '__all__':
                    messages.error(request, f"Error: {error}")
                else:
                    field_name = form.fields[field].label or field.replace('_', ' ').title()
                    messages.error(request, f"{field_name}: {error}")
    
    # Always redirect back to farm management page
    return redirect('monitoring:farm_management')

@login_required
def farm_detail(request, farm_id):
    """View individual farm details"""
    try:
        farm = Farm.objects.get(id=farm_id, manager=request.user, is_active=True)
        
        # Get farm statistics
        farm_fields = farm.field_set.all()
        field_count = farm_fields.count()
        
        farm_area_hectares = farm_fields.aggregate(
            total=Sum('area_hectares')
        )['total'] or farm.total_area_hectares
        
        total_area_acres = farm_area_hectares * Decimal('2.47105')
        
        total_harvested = HarvestRecord.objects.filter(
            field__farm=farm
        ).aggregate(total=Sum('quantity_tons'))['total'] or Decimal('0')
        
        avg_yield = total_harvested / total_area_acres if total_area_acres > 0 else Decimal('0')
        
        farm.calculated_field_count = field_count
        farm.calculated_total_area = total_area_acres
        farm.calculated_total_harvested = total_harvested
        farm.calculated_avg_yield = avg_yield
        
        context = {
            'farm': farm,
            'fields': farm_fields
        }
        return render(request, 'monitoring/farm_detail.html', context)
        
    except Farm.DoesNotExist:
        messages.error(request, "Farm not found or you don't have permission to view it.")
        return redirect('monitoring:farm_management')

@login_required
def farm_edit(request, farm_id):
    """Edit farm details"""
    try:
        farm = Farm.objects.get(id=farm_id, manager=request.user, is_active=True)
        
        if request.method == "POST":
            form = FarmForm(request.POST, instance=farm)
            if form.is_valid():
                updated_farm = form.save(commit=False)
                updated_farm.manager = request.user
                updated_farm.save()
                
                # Handle crop types
                crop_types = request.POST.getlist('crop_types')
                if crop_types:
                    # Update crop types in notes
                    base_notes = updated_farm.notes.split('\nCrops:')[0] if updated_farm.notes else ""
                    updated_farm.notes = f"{base_notes}\nCrops: {', '.join(crop_types)}"
                    updated_farm.save()
                
                messages.success(request, f"Farm '{updated_farm.name}' updated successfully!")
                return redirect('monitoring:farm_management')
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        field_name = form.fields[field].label or field.replace('_', ' ').title()
                        messages.error(request, f"{field_name}: {error}")
        else:
            form = FarmForm(instance=farm)
        
        context = {
            'form': form,
            'farm': farm,
            'editing': True
        }
        return render(request, 'monitoring/farm_edit.html', context)
        
    except Farm.DoesNotExist:
        messages.error(request, "Farm not found or you don't have permission to edit it.")
        return redirect('monitoring:farm_management')

@login_required
def farm_delete(request, farm_id):
    """Soft delete a farm (set is_active=False)"""
    try:
        farm = Farm.objects.get(id=farm_id, manager=request.user, is_active=True)
        farm_name = farm.name
        
        # Soft delete - set is_active to False instead of actually deleting
        farm.is_active = False
        farm.save()
        
        messages.success(request, f"Farm '{farm_name}' has been deactivated successfully!")
        
    except Farm.DoesNotExist:
        messages.error(request, "Farm not found or you don't have permission to delete it.")
    
    return redirect('monitoring:farm_management')

# Alternative hard delete function if needed
@login_required
def farm_hard_delete(request, farm_id):
    """Permanently delete a farm (use with caution)"""
    try:
        farm = Farm.objects.get(id=farm_id, manager=request.user)
        farm_name = farm.name
        farm.delete()
        
        messages.success(request, f"Farm '{farm_name}' deleted permanently!")
        
    except Farm.DoesNotExist:
        messages.error(request, "Farm not found or you don't have permission to delete it.")
    
    return redirect('monitoring:farm_management')
# ========================
# HARVEST TRACKING VIEWS
# ========================
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum
from datetime import datetime, timedelta
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
import json

@login_required
@admin_added_required
def harvest_tracking(request):
    """Enhanced Harvest Tracking view with CRUD operations"""
    
    # Handle POST requests for CRUD operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            return create_harvest_record(request)
        elif action == 'edit':
            return update_harvest_record(request)
        elif action == 'delete':
            return delete_harvest_record(request)
    
    # Handle GET request filtering
    filter_type = request.GET.get('filter', 'all')
    
    # Base queryset
    harvests = HarvestRecord.objects.select_related(
        'field__farm', 'field__crop', 'harvested_by'
    ).order_by('-harvest_date')
    
    # Apply filters
    if filter_type == 'today':
        today = datetime.now().date()
        harvests = harvests.filter(harvest_date=today)
    elif filter_type == 'corn':
        harvests = harvests.filter(field__crop__name__icontains='corn')
    elif filter_type == 'wheat':
        harvests = harvests.filter(field__crop__name__icontains='wheat')
    elif filter_type == 'soybeans':
        harvests = harvests.filter(field__crop__name__icontains='soybean')
    elif filter_type == 'rice':
        harvests = harvests.filter(field__crop__name__icontains='rice')
    
    # Limit to 50 for performance
    total_records = harvests.count()
    harvests = harvests[:50]
    
    # Calculate statistics
    all_harvests = HarvestRecord.objects.all()
    total_quantity = all_harvests.aggregate(
        total=Sum('quantity_tons')
    )['total'] or 0
    
    # Status-based metrics (add status field to model if not exists)
    completed_harvests = all_harvests.filter(
        harvest_date__lte=datetime.now().date()
    ).count()
    
    # In progress (harvests from last 7 days)
    week_ago = datetime.now().date() - timedelta(days=7)
    in_progress_harvests = all_harvests.filter(
        harvest_date__gte=week_ago,
        harvest_date__lte=datetime.now().date()
    ).count()
    
    # Calculate average quality
    quality_grades = all_harvests.values_list('quality_grade', flat=True)
    avg_quality = 'A'
    if quality_grades:
        from collections import Counter
        grade_counts = Counter(quality_grades)
        avg_quality = grade_counts.most_common(1)[0][0] if grade_counts else 'A'
    
    # Get available fields and users for the form
    available_fields = Field.objects.select_related('farm', 'crop').filter(
        is_active=True
    ).order_by('farm__name', 'name')
    
    # Debug: Print field count
    print(f"DEBUG: Total fields in database: {Field.objects.count()}")
    print(f"DEBUG: Active fields: {available_fields.count()}")
    
    available_users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    
    context = {
        'harvests': harvests,
        'total_quantity': float(total_quantity),
        'completed_harvests': completed_harvests,
        'in_progress_harvests': in_progress_harvests,
        'avg_quality': avg_quality,
        'available_fields': available_fields,
        'available_users': available_users,
        'filter_type': filter_type,
        'total_records': total_records,
        'total_harvest_records': all_harvests.count(),
    }
    
    return render(request, 'monitoring/harvest_tracking.html', context)


def create_harvest_record(request):
    """Create a new harvest record"""
    try:
        field_id = request.POST.get('field')
        harvested_by_id = request.POST.get('harvested_by')
        harvest_date = request.POST.get('harvest_date')
        quantity = request.POST.get('quantity')
        quality_grade = request.POST.get('quality_grade')
        weather = request.POST.get('weather', '')
        notes = request.POST.get('notes', '')
        
        # Validation
        if not all([field_id, harvested_by_id, harvest_date, quantity, quality_grade]):
            messages.error(request, 'Please fill in all required fields.')
            return redirect('harvest_tracking')
        
        # Get related objects
        field = get_object_or_404(Field, id=field_id)
        harvested_by = get_object_or_404(User, id=harvested_by_id)
        
        # Convert and validate data
        try:
            quantity_tons = float(quantity)
            harvest_date_obj = datetime.strptime(harvest_date, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Invalid date or quantity format.')
            return redirect("monitoring:harvest_tracking")
        
        # Create harvest record
        harvest_record = HarvestRecord.objects.create(
            field=field,
            harvested_by=harvested_by,
            harvest_date=harvest_date_obj,
            quantity_tons=quantity_tons,
            quality_grade=quality_grade.upper(),
            weather_conditions=weather,
            notes=notes,
            created_by=request.user
        )
        
        messages.success(request, f'Harvest record created successfully! {quantity_tons} tons of {field.crop.name} recorded.')
        
    except Exception as e:
        messages.error(request, f'Error creating harvest record: {str(e)}')
    
    return redirect("monitoring:harvest_tracking")


def update_harvest_record(request):
    """Update an existing harvest record"""
    try:
        harvest_id = request.POST.get('harvest_id')
        if not harvest_id:
            messages.error(request, 'Invalid harvest record.')
            return redirect("monitoring:harvest_tracking")
        
        harvest_record = get_object_or_404(HarvestRecord, id=harvest_id)
        
        # Update fields
        field_id = request.POST.get('field')
        harvested_by_id = request.POST.get('harvested_by')
        harvest_date = request.POST.get('harvest_date')
        quantity = request.POST.get('quantity')
        quality_grade = request.POST.get('quality_grade')
        weather = request.POST.get('weather', '')
        notes = request.POST.get('notes', '')
        
        # Validation
        if not all([field_id, harvested_by_id, harvest_date, quantity, quality_grade]):
            messages.error(request, 'Please fill in all required fields.')
            return redirect("monitoring:harvest_tracking")
        
        # Get related objects
        field = get_object_or_404(Field, id=field_id)
        harvested_by = get_object_or_404(User, id=harvested_by_id)
        
        # Convert and validate data
        try:
            quantity_tons = float(quantity)
            harvest_date_obj = datetime.strptime(harvest_date, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Invalid date or quantity format.')
            return redirect("monitoring:harvest_tracking")
        
        # Update harvest record
        harvest_record.field = field
        harvest_record.harvested_by = harvested_by
        harvest_record.harvest_date = harvest_date_obj
        harvest_record.quantity_tons = quantity_tons
        harvest_record.quality_grade = quality_grade.upper()
        harvest_record.weather_conditions = weather
        harvest_record.notes = notes
        harvest_record.save()
        
        messages.success(request, f'Harvest record updated successfully!')
        
    except Exception as e:
        messages.error(request, f'Error updating harvest record: {str(e)}')
    
    return redirect('"monitoring:harvest_tracking"')


def delete_harvest_record(request):
    """Delete a harvest record"""
    try:
        harvest_id = request.POST.get('harvest_id')
        if not harvest_id:
            messages.error(request, 'Invalid harvest record.')
            return redirect('harvest_tracking')
        
        harvest_record = get_object_or_404(HarvestRecord, id=harvest_id)
        
        # Store info for success message
        field_name = f"{harvest_record.field.farm.name} - {harvest_record.field.name}"
        quantity = harvest_record.quantity_tons
        
        # Delete the record
        harvest_record.delete()
        
        messages.success(request, f'Harvest record for {field_name} ({quantity} tons) deleted successfully.')
        
    except Exception as e:
        messages.error(request, f'Error deleting harvest record: {str(e)}')
    
    return redirect("monitoring:harvest_tracking")


@login_required
@require_http_methods(["GET"])
def harvest_details(request, harvest_id):
    """Get harvest details for view/edit operations (AJAX endpoint)"""
    try:
        harvest = get_object_or_404(HarvestRecord, id=harvest_id)
        
        data = {
            'success': True,
            'data': {
                'id': harvest.id,
                'field_id': harvest.field.id,
                'field_name': f"{harvest.field.farm.name} - {harvest.field.name}",
                'crop_name': harvest.field.crop.name if harvest.field.crop else '',
                'harvested_by_id': harvest.harvested_by.id if harvest.harvested_by else '',
                'harvested_by_name': f"{harvest.harvested_by.first_name} {harvest.harvested_by.last_name}" if harvest.harvested_by else '',
                'harvest_date': harvest.harvest_date.strftime('%Y-%m-%d'),
                'quantity_tons': float(harvest.quantity_tons),
                'quality_grade': harvest.quality_grade,
                'weather_conditions': harvest.weather_conditions or '',
                'notes': harvest.notes or '',
                'created_at': harvest.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(harvest, 'created_at') else '',
            }
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_http_methods(["GET"])
def harvest_summary_stats(request):
    """Get summary statistics for dashboard (AJAX endpoint)"""
    try:
        # Date ranges
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Calculate stats
        total_harvests = HarvestRecord.objects.count()
        total_quantity = HarvestRecord.objects.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        week_quantity = HarvestRecord.objects.filter(
            harvest_date__gte=week_ago
        ).aggregate(total=Sum('quantity_tons'))['total'] or 0
        
        month_quantity = HarvestRecord.objects.filter(
            harvest_date__gte=month_ago
        ).aggregate(total=Sum('quantity_tons'))['total'] or 0
        
        # Top performing fields
        top_fields = Field.objects.annotate(
            total_harvest=Sum('harvestrecord__quantity_tons')
        ).filter(total_harvest__gt=0).order_by('-total_harvest')[:5]
        
        # Quality distribution
        quality_stats = {}
        for grade in ['A', 'B', 'C']:
            count = HarvestRecord.objects.filter(quality_grade=grade).count()
            quality_stats[f'grade_{grade}'] = count
        
        data = {
            'success': True,
            'stats': {
                'total_harvests': total_harvests,
                'total_quantity': float(total_quantity),
                'week_quantity': float(week_quantity),
                'month_quantity': float(month_quantity),
                'quality_distribution': quality_stats,
                'top_fields': [
                    {
                        'name': f"{field.farm.name} - {field.name}",
                        'total': float(field.total_harvest)
                    } for field in top_fields
                ]
            }
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


# ========================
# ANALYTICS VIEWS
# ========================

@login_required
@admin_added_required
def analytics(request):
    """Analytics view - detailed charts and analysis"""
    try:
        current_year = datetime.now().year
        current_date = datetime.now().date()
        
        # Get all active farms with their efficiency data
        farms_data = []
        total_efficiency = 0
        underperforming_count = 0
        
        for farm in Farm.objects.filter(is_active=True).prefetch_related('field_set__crop'):
            expected_total = 0
            for field in farm.field_set.all():
                if field.crop.expected_yield_per_hectare:
                    expected_total += float(field.area_hectares * field.crop.expected_yield_per_hectare)
                else:
                    expected_total += float(field.area_hectares * 5)
            
            actual_total = float(HarvestRecord.objects.filter(
                field__farm=farm
            ).aggregate(total=Sum('quantity_tons'))['total'] or 0)
            
            if expected_total > 0:
                efficiency = min((actual_total / expected_total) * 100, 100)
            else:
                efficiency = 0
            
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
        
        avg_efficiency = total_efficiency / len(farms_data) if farms_data else 85.0
        
        top_performer = max(farms_data, key=lambda x: x['efficiency']) if farms_data else {
            'name': 'No Data', 'efficiency': 0
        }
        
        # Calculate predicted harvest
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
        
        # Yield Performance Chart Data
        yield_performance_data = []
        for farm_data in farms_data[:8]:
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
        
        # Seasonal Trends Data
        seasonal_trends_data = {'corn': [], 'wheat': [], 'soybeans': []}
        
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
        
        # Weather Correlation Data
        weather_correlation_data = {'performance': [], 'rainfall': []}
        
        for month in range(1, 9):
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
                performance = random.randint(70, 95)
            
            weather_correlation_data['performance'].append(round(performance, 1))
            weather_correlation_data['rainfall'].append(round(random.uniform(1.5, 7.5), 1))
        
        # Farm Rankings
        farm_rankings = sorted(farms_data, key=lambda x: x['efficiency'], reverse=True)[:10]
        
        # Harvest Predictions
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
            
            confidence = 85
            
            harvest_count = field.harvestrecord_set.count()
            if harvest_count > 3:
                confidence += 5
            elif harvest_count > 1:
                confidence += 3
            
            if field.crop.expected_yield_per_hectare:
                confidence += 5
            
            confidence += random.randint(-3, 8)
            confidence = min(max(confidence, 80), 98)
            
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
        print(f"Analytics view error: {e}")
        
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


# ========================
# INVENTORY MANAGEMENT VIEWS
# ========================

@login_required
@admin_added_required
def inventory(request):
    """Main inventory management view with filtering and CRUD operations"""
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
        'inventory_items': inventory_items[:50],
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
@admin_added_required
def add_inventory(request):
    """Add new inventory item"""
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
@admin_added_required
def remove_inventory(request):
    """Remove inventory items"""
    if request.method == 'POST':
        form = RemoveInventoryForm(request.POST)
        if form.is_valid():
            crop = form.cleaned_data['crop']
            storage_location = form.cleaned_data['storage_location']
            quantity_to_remove = form.cleaned_data['quantity_tons']
            reason = form.cleaned_data.get('reason', '')
            
            try:
                with transaction.atomic():
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
                    
                    for item in inventory_items:
                        if remaining_to_remove <= 0:
                            break
                        
                        if item.quantity_tons <= remaining_to_remove:
                            remaining_to_remove -= item.quantity_tons
                            items_updated.append(f"Removed all {item.quantity_tons} tons from {item.batch_number or 'batch'}")
                            item.delete()
                        else:
                            removed_amount = remaining_to_remove
                            item.quantity_tons -= remaining_to_remove
                            if hasattr(item, 'notes'):
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
@admin_added_required
def get_inventory_locations(request):
    """AJAX endpoint to get available storage locations for a specific crop"""
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
@admin_added_required
def inventory_summary(request):
    """Get inventory summary data for dashboard"""
    total_quantity = Inventory.objects.aggregate(total=Sum('quantity_tons'))['total'] or 0
    total_items = Inventory.objects.count()
    total_value = Inventory.objects.aggregate(
        total=Sum(F('quantity_tons') * F('unit_price'))
    )['total'] or 0
    
    thirty_days = date.today() + timedelta(days=30)
    low_stock_count = Inventory.objects.filter(quantity_tons__lt=10).count()
    expiring_count = Inventory.objects.filter(
        expiry_date__lte=thirty_days,
        expiry_date__gt=date.today()
    ).count()
    
    top_crops = Inventory.objects.values('crop__name').annotate(
        total_quantity=Sum('quantity_tons')
    ).order_by('-total_quantity')[:5]
    
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
@admin_added_required
def bulk_update_inventory(request):
    """Bulk update inventory items"""
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
@admin_added_required
def export_inventory(request):
    """Export inventory data to CSV"""
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
        if hasattr(item, 'is_expired') and item.is_expired:
            status = 'Expired'
        elif hasattr(item, 'days_until_expiry') and item.days_until_expiry and item.days_until_expiry <= 30:
            status = 'Expiring Soon'
        elif hasattr(item, 'is_low_stock') and item.is_low_stock:
            status = 'Low Stock'
        
        writer.writerow([
            item.crop.name,
            item.quantity_tons,
            item.storage_location,
            item.get_quality_grade_display() if hasattr(item, 'get_quality_grade_display') else item.quality_grade,
            item.date_stored,
            item.expiry_date or '',
            item.get_storage_condition_display() if hasattr(item, 'get_storage_condition_display') else getattr(item, 'storage_condition', ''),
            getattr(item, 'batch_number', '') or '',
            getattr(item, 'unit_price', '') or '',
            getattr(item, 'total_value', '') or '',
            item.managed_by.get_full_name() or item.managed_by.username,
            status
        ])
    
    return response


# ========================
# REPORTING VIEWS
# ========================

@login_required
@admin_added_required
def reports(request):
    """Reports view - generate various reports"""
    current_month = timezone.now().replace(day=1)
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
@admin_added_required
def generate_report(request):
    """Generate custom reports based on user input"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        report_type = request.POST.get('report_type')
        from_date = request.POST.get('from_date')
        to_date = request.POST.get('to_date')
        export_format = request.POST.get('export_format')
        
        if not all([report_type, from_date, to_date, export_format]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'})
        
        from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        if from_date > to_date:
            return JsonResponse({'success': False, 'error': 'Invalid date range'})
        
        if report_type == 'monthly_harvest_summary':
            return generate_harvest_summary_report(from_date, to_date, export_format)
        elif report_type == 'yield_performance_report':
            return generate_yield_performance_report(from_date, to_date, export_format)
        elif report_type == 'inventory_status_report':
            return generate_inventory_status_report(from_date, to_date, export_format)
        elif report_type == 'farm_productivity_analysis':
            return generate_farm_productivity_report(from_date, to_date, export_format)
        else:
            return JsonResponse({'success': False, 'error': 'Invalid report type'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def generate_harvest_summary_report(from_date, to_date, export_format):
    """Generate monthly harvest summary report"""
    harvests = HarvestRecord.objects.filter(
        harvest_date__range=[from_date, to_date]
    ).select_related('field', 'field__farm', 'field__crop', 'harvested_by')
    
    total_quantity = harvests.aggregate(total=Sum('quantity_tons'))['total'] or Decimal('0')
    total_harvests = harvests.count()
    
    farm_data = {}
    for harvest in harvests:
        farm_name = harvest.field.farm.name
        if farm_name not in farm_data:
            farm_data[farm_name] = {
                'total_quantity': Decimal('0'),
                'harvest_count': 0,
                'fields': set(),
                'crops': set()
            }
        farm_data[farm_name]['total_quantity'] += harvest.quantity_tons
        farm_data[farm_name]['harvest_count'] += 1
        farm_data[farm_name]['fields'].add(harvest.field.name)
        farm_data[farm_name]['crops'].add(harvest.field.crop.name)
    
    if export_format == 'pdf':
        return generate_pdf_harvest_report(farm_data, total_quantity, total_harvests, from_date, to_date)
    elif export_format == 'excel':
        return generate_excel_harvest_report(farm_data, harvests, from_date, to_date)
    elif export_format == 'csv':
        return generate_csv_harvest_report(harvests, from_date, to_date)


def generate_csv_harvest_report(harvests, from_date, to_date):
    """Generate CSV harvest summary report"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="harvest_summary_{from_date}_{to_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Farm', 'Field', 'Crop', 'Quantity (tons)', 'Quality Grade', 'Harvested By', 'Weather Conditions'])
    
    for harvest in harvests:
        writer.writerow([
            harvest.harvest_date.strftime('%Y-%m-%d'),
            harvest.field.farm.name,
            harvest.field.name,
            harvest.field.crop.name,
            harvest.quantity_tons,
            harvest.quality_grade,
            harvest.harvested_by.get_full_name(),
            getattr(harvest, 'weather_conditions', 'N/A') or 'N/A'
        ])
    
    return response


def generate_pdf_harvest_report(farm_data, total_quantity, total_harvests, from_date, to_date):
    """Generate PDF harvest summary report"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title = Paragraph(f"Harvest Summary Report", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 20))
    
    # Date range
    date_range = Paragraph(f"Period: {from_date.strftime('%B %d, %Y')} - {to_date.strftime('%B %d, %Y')}", styles['Normal'])
    story.append(date_range)
    story.append(Spacer(1, 20))
    
    # Summary statistics
    summary_data = [
        ['Metric', 'Value'],
        ['Total Harvests', str(total_harvests)],
        ['Total Quantity', f"{total_quantity} tons"],
        ['Number of Farms', str(len(farm_data))],
    ]
    
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 30))
    
    # Farm breakdown
    if farm_data:
        farm_title = Paragraph("Farm Breakdown", styles['Heading2'])
        story.append(farm_title)
        story.append(Spacer(1, 12))
        
        farm_table_data = [['Farm Name', 'Total Quantity (tons)', 'Harvest Count', 'Fields', 'Crops']]
        
        for farm_name, data in farm_data.items():
            farm_table_data.append([
                farm_name,
                str(data['total_quantity']),
                str(data['harvest_count']),
                str(len(data['fields'])),
                str(len(data['crops']))
            ])
        
        farm_table = Table(farm_table_data)
        farm_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(farm_table)
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="harvest_summary_{from_date}_{to_date}.pdf"'
    return response


def generate_excel_harvest_report(farm_data, harvests, from_date, to_date):
    """Generate Excel harvest summary report"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Harvest Summary"
    
    # Header style
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    center_alignment = Alignment(horizontal="center")
    
    # Title and date range
    ws['A1'] = "Harvest Summary Report"
    ws['A1'].font = Font(bold=True, size=16)
    ws['A2'] = f"Period: {from_date.strftime('%B %d, %Y')} - {to_date.strftime('%B %d, %Y')}"
    
    # Farm summary headers
    headers = ['Farm Name', 'Total Quantity (tons)', 'Harvest Count', 'Number of Fields', 'Number of Crops']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_alignment
    
    # Farm data
    row = 5
    for farm_name, data in farm_data.items():
        ws.cell(row=row, column=1).value = farm_name
        ws.cell(row=row, column=2).value = float(data['total_quantity'])
        ws.cell(row=row, column=3).value = data['harvest_count']
        ws.cell(row=row, column=4).value = len(data['fields'])
        ws.cell(row=row, column=5).value = len(data['crops'])
        row += 1
    
    # Individual harvests sheet
    ws2 = wb.create_sheet("Individual Harvests")
    harvest_headers = ['Date', 'Farm', 'Field', 'Crop', 'Quantity (tons)', 'Quality Grade', 'Harvested By']
    
    for col, header in enumerate(harvest_headers, 1):
        cell = ws2.cell(row=1, column=col)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_alignment
    
    row = 2
    for harvest in harvests:
        ws2.cell(row=row, column=1).value = harvest.harvest_date.strftime('%Y-%m-%d')
        ws2.cell(row=row, column=2).value = harvest.field.farm.name
        ws2.cell(row=row, column=3).value = harvest.field.name
        ws2.cell(row=row, column=4).value = harvest.field.crop.name
        ws2.cell(row=row, column=5).value = float(harvest.quantity_tons)
        ws2.cell(row=row, column=6).value = harvest.quality_grade
        ws2.cell(row=row, column=7).value = harvest.harvested_by.get_full_name()
        row += 1
    
    # Auto-adjust column widths
    for ws in wb.worksheets:
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
    
    # Save to buffer
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="harvest_summary_{from_date}_{to_date}.xlsx"'
    return response


def generate_yield_performance_report(from_date, to_date, export_format):
    """Generate yield performance report comparing actual vs expected yields"""
    harvests = HarvestRecord.objects.filter(
        harvest_date__range=[from_date, to_date]
    ).select_related('field', 'field__farm', 'field__crop')
    
    performance_data = []
    for harvest in harvests:
        expected_yield = getattr(harvest.field, 'expected_yield_total', 0) or 0
        actual_yield = harvest.quantity_tons
        performance_percentage = (actual_yield / expected_yield * 100) if expected_yield > 0 else 0
        
        performance_data.append({
            'farm': harvest.field.farm.name,
            'field': harvest.field.name,
            'crop': harvest.field.crop.name,
            'expected_yield': expected_yield,
            'actual_yield': actual_yield,
            'performance_percentage': performance_percentage,
            'harvest_date': harvest.harvest_date
        })
    
    if export_format == 'csv':
        return generate_csv_yield_report(performance_data, from_date, to_date)
    
    return JsonResponse({'success': True, 'message': 'Report generated successfully'})


def generate_csv_yield_report(performance_data, from_date, to_date):
    """Generate CSV yield performance report"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="yield_performance_{from_date}_{to_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Farm', 'Field', 'Crop', 'Expected Yield (tons)', 'Actual Yield (tons)', 
        'Performance (%)', 'Harvest Date'
    ])
    
    for data in performance_data:
        writer.writerow([
            data['farm'],
            data['field'],
            data['crop'],
            data['expected_yield'],
            data['actual_yield'],
            round(data['performance_percentage'], 2),
            data['harvest_date'].strftime('%Y-%m-%d')
        ])
    
    return response


def generate_inventory_status_report(from_date, to_date, export_format):
    """Generate inventory status report"""
    inventory_items = Inventory.objects.filter(
        date_stored__range=[from_date, to_date]
    ).select_related('crop', 'managed_by')
    
    if export_format == 'csv':
        return generate_csv_inventory_report(inventory_items, from_date, to_date)
    
    return JsonResponse({'success': True, 'message': 'Report generated successfully'})


def generate_csv_inventory_report(inventory_items, from_date, to_date):
    """Generate CSV inventory status report"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="inventory_status_{from_date}_{to_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Crop', 'Quantity (tons)', 'Storage Location', 'Storage Condition', 
        'Quality Grade', 'Date Stored', 'Expiry Date', 'Days in Storage', 
        'Unit Price', 'Total Value', 'Status'
    ])
    
    for item in inventory_items:
        status = []
        if hasattr(item, 'is_reserved') and item.is_reserved:
            status.append('Reserved')
        if hasattr(item, 'is_expired') and item.is_expired:
            status.append('Expired')
        elif hasattr(item, 'expiry_date') and item.expiry_date and item.expiry_date < date.today():
            status.append('Expired')
        if hasattr(item, 'is_low_stock') and item.is_low_stock:
            status.append('Low Stock')
        elif item.quantity_tons < 10:
            status.append('Low Stock')
        if not status:
            status.append('Good')
            
        days_in_storage = (date.today() - item.date_stored).days if item.date_stored else 0
            
        writer.writerow([
            item.crop.name,
            item.quantity_tons,
            item.storage_location,
            getattr(item, 'storage_condition', 'N/A'),
            item.quality_grade,
            item.date_stored.strftime('%Y-%m-%d'),
            item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else 'N/A',
            days_in_storage,
            getattr(item, 'unit_price', 'N/A') or 'N/A',
            getattr(item, 'total_value', 'N/A') or 'N/A',
            ', '.join(status)
        ])
    
    return response


def generate_farm_productivity_report(from_date, to_date, export_format):
    """Generate farm productivity analysis report"""
    farms = Farm.objects.all()
    
    productivity_data = []
    for farm in farms:
        total_harvested = farm.field_set.filter(
            harvestrecord__harvest_date__range=[from_date, to_date]
        ).aggregate(total=Sum('harvestrecord__quantity_tons'))['total'] or Decimal('0')
        
        efficiency = getattr(farm, 'efficiency_percentage', 0) or 0
        total_fields = farm.field_set.count()
        active_fields = farm.field_set.filter(is_active=True).count()
        primary_crop = getattr(farm, 'primary_crop', 'Mixed') or 'Mixed'
        
        productivity_data.append({
            'farm_name': farm.name,
            'location': farm.location,
            'total_area': farm.total_area_hectares,
            'total_harvested': total_harvested,
            'efficiency_percentage': efficiency,
            'total_fields': total_fields,
            'active_fields': active_fields,
            'primary_crop': primary_crop
        })
    
    if export_format == 'csv':
        return generate_csv_productivity_report(productivity_data, from_date, to_date)
    
    return JsonResponse({'success': True, 'message': 'Report generated successfully'})


def generate_csv_productivity_report(productivity_data, from_date, to_date):
    """Generate CSV productivity report"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="farm_productivity_{from_date}_{to_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Farm Name', 'Location', 'Total Area (hectares)', 'Total Harvested (tons)',
        'Efficiency (%)', 'Total Fields', 'Active Fields', 'Primary Crop'
    ])
    
    for data in productivity_data:
        writer.writerow([
            data['farm_name'],
            data['location'],
            data['total_area'],
            data['total_harvested'],
            round(data['efficiency_percentage'], 2),
            data['total_fields'],
            data['active_fields'],
            data['primary_crop']
        ])
    
    return response


# ========================
# NOTIFICATIONS AND MISCELLANEOUS VIEWS
# ========================

@login_required
@admin_added_required
def notifications(request):
    """Notifications view - show system notifications"""
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


# ========================
# API ENDPOINTS
# ========================

@login_required
@role_required(['admin'])
@csrf_exempt
def api_user_toggle_status(request, user_id):
    """Toggle user active status via API"""
    if request.method == 'POST':
        try:
            user = get_object_or_404(User, id=user_id)
            
            if user.is_superuser and not request.user.is_superuser:
                return JsonResponse({
                    'success': False,
                    'message': 'You cannot modify superuser accounts.'
                })
            
            if user == request.user:
                return JsonResponse({
                    'success': False,
                    'message': 'You cannot modify your own account status.'
                })
            
            new_status = not user.userprofile.is_active
            user.userprofile.is_active = new_status
            user.userprofile.save()
            user.is_active = new_status
            user.save()
            
            return JsonResponse({
                'success': True,
                'message': f'User {user.username} has been {"activated" if new_status else "deactivated"}.',
                'new_status': new_status
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


def get_yearly_trends(request, year):
    """API endpoint to get seasonal trends for a specific year"""
    try:
        trends_data = {}
        
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
        
        fields_data = []
        total_expected = 0
        total_actual = 0
        
        for field in farm.field_set.all():
            field_expected = float(field.area_hectares * (field.crop.expected_yield_per_hectare or 5))
            field_actual = float(HarvestRecord.objects.filter(field=field).aggregate(
                total=Sum('quantity_tons')
            )['total'] or 0)
            
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
        total_harvests = HarvestRecord.objects.count()
        active_farms = Farm.objects.filter(is_active=True).count()
        total_inventory = Inventory.objects.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        week_ago = datetime.now().date() - timedelta(days=7)
        recent_harvests = HarvestRecord.objects.filter(
            harvest_date__gte=week_ago
        ).count()
        
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
        
        
        




@login_required
@admin_added_required
def settings_view(request):
    """Settings view for system configuration"""
    context = {
        'user': request.user,
        'system_info': {
            'version': '1.0.0',
            'last_updated': datetime.now().strftime('%Y-%m-%d'),
            'total_users': User.objects.count(),
            'total_farms': Farm.objects.count(),
            'total_harvests': HarvestRecord.objects.count(),
        }
    }
    return render(request, 'monitoring/settings.html', context)




def user_add(request):
    if request.method == "POST":
        form = UserAddForm(request.POST)
        if form.is_valid():
            try:
                # Create the user
                user = form.save(commit=False)
                user.set_password(form.cleaned_data['password'])
                user.save()

                # Create UserProfile with selected role
                is_active = form.cleaned_data['status'] == 'active'
                user_profile = UserProfile.objects.create(
                    user=user,
                    role=form.cleaned_data['role'],
                    is_active=is_active
                )

                # Handle farm access (you might want to store this in a separate model)
                farm_access = form.cleaned_data.get('farm_access', [])
                # You can store farm_access in the UserProfile model or create a separate FarmAccess model

                # Add success message for the redirect
                user_display_name = user.get_full_name() or user.username
                messages.success(
                    request, 
                    f'User "{user_display_name}" has been created successfully! Role: {user_profile.get_role_display()}'
                )
                
                # Redirect with a success flag in URL
                return redirect(f"{reverse('monitoring:user_management')}?user_created=success")
                
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
                
    else:
        form = UserAddForm()
    
    return render(request, 'monitoring/user_add.html', {'form': form})

