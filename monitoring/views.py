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
from .models import Farm, HarvestRecord,ReportTemplate, GeneratedReport, ReportActivityLog
import os
from django.views.decorators.http import require_POST

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
# monitoring/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Q, F, Count
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import date, timedelta
import json
import csv

from .models import InventoryItem, StorageLocation, CropType, InventoryTransaction
from .forms import AddInventoryForm, RemoveInventoryForm, InventoryFilterForm, StorageLocationForm, CropTypeForm

@login_required
def inventory_dashboard(request):
    """Main inventory dashboard view"""
    
    # Check permissions - adjust this based on your permission system
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager', 'inventory_manager']
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            messages.error(request, "You don't have permission to access inventory management.")
            return redirect('monitoring:dashboard')
    
    # Get filter form
    filter_form = InventoryFilterForm(request.GET)
    
    # Base queryset
    inventory_items = InventoryItem.objects.select_related(
        'crop_type', 'storage_location', 'added_by'
    ).prefetch_related('transactions')
    
    # Apply filters
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('crop_type'):
            inventory_items = inventory_items.filter(crop_type=filter_form.cleaned_data['crop_type'])
        
        if filter_form.cleaned_data.get('storage_location'):
            inventory_items = inventory_items.filter(storage_location=filter_form.cleaned_data['storage_location'])
        
        if filter_form.cleaned_data.get('quality_grade'):
            inventory_items = inventory_items.filter(quality_grade=filter_form.cleaned_data['quality_grade'])
        
        if filter_form.cleaned_data.get('status'):
            status = filter_form.cleaned_data['status']
            if status == 'expiring':
                # Items expiring within 30 days
                expiry_threshold = date.today() + timedelta(days=30)
                inventory_items = inventory_items.filter(
                    expiry_date__lte=expiry_threshold,
                    expiry_date__gte=date.today()
                )
            elif status == 'expired':
                inventory_items = inventory_items.filter(expiry_date__lt=date.today())
    
    # Get all items for status calculation and pagination
    inventory_list = list(inventory_items)
    
    # Filter low stock items if needed (requires status property calculation)
    if filter_form.is_valid() and filter_form.cleaned_data.get('status') == 'low_stock':
        inventory_list = [item for item in inventory_list if item.status == 'low_stock']
    
    # Pagination
    paginator = Paginator(inventory_list, 10)  # 10 items per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # CALCULATE DASHBOARD STATISTICS DIRECTLY (Fixed section)
    all_inventory_items = InventoryItem.objects.select_related('crop_type', 'storage_location')
    
    # 1. Total Inventory (sum of all quantities)
    total_inventory = all_inventory_items.aggregate(total=Sum('quantity'))['total'] or 0
    
    # 2. Storage Locations count (count unique active storage locations that have inventory)
    storage_locations_count = all_inventory_items.values('storage_location').distinct().count()
    
    # 3. Low Stock and Expiring items counts
    low_stock_count = 0
    expiring_count = 0
    expiry_threshold = date.today() + timedelta(days=30)
    
    for item in all_inventory_items:
        # Check if expiring within 30 days
        if item.expiry_date and item.expiry_date <= expiry_threshold and item.expiry_date >= date.today():
            expiring_count += 1
        
        # Check for low stock - you'll need to define what constitutes "low stock"
        # Option 1: If you have a minimum_stock_threshold field on crop_type
        if hasattr(item.crop_type, 'minimum_stock_threshold') and item.crop_type.minimum_stock_threshold:
            if item.quantity <= item.crop_type.minimum_stock_threshold:
                low_stock_count += 1
        # Option 2: Use a fixed threshold (e.g., less than 50 tons is low stock)
        elif item.quantity < 50:  # Adjust this threshold as needed
            low_stock_count += 1
    
    # Create stats dictionary with exact template key names
    stats = {
        'total_inventory': round(float(total_inventory), 1),
        'storage_locations': storage_locations_count,  # Template expects this key
        'low_stock_items': low_stock_count,  # Template expects this key
        'expiring_items': expiring_count  # Template expects this key
    }
    
    # Debug print (remove after testing)
    print(f"DEBUG - Stats calculated: {stats}")
    print(f"DEBUG - Storage locations: {storage_locations_count}")
    print(f"DEBUG - Low stock items: {low_stock_count}")
    print(f"DEBUG - Expiring items: {expiring_count}")
    
    # Get recent transactions
    recent_transactions = InventoryTransaction.objects.select_related(
        'user', 'inventory_item__crop_type', 'inventory_item__storage_location'
    )[:10]
    
    # Create forms
    add_form = AddInventoryForm()
    remove_form = RemoveInventoryForm()
    
    # Check permissions for template
    can_manage_inventory = (
        request.user.is_superuser or 
        (user_profile and hasattr(user_profile, 'role') and user_profile.role in allowed_roles)
    )
    
    context = {
        'inventory_items': page_obj,
        'stats': stats,  # Now calculated dynamically
        'recent_transactions': recent_transactions,
        'filter_form': filter_form,
        'add_form': add_form,
        'remove_form': remove_form,
        'storage_locations': StorageLocation.objects.filter(is_active=True),
        'crop_types': CropType.objects.filter(is_active=True),
        'perms': {'can_manage_inventory': can_manage_inventory}
    }
    
    return render(request, 'monitoring/inventory.html', context)


@login_required
@require_POST
def add_inventory(request):
    """Add new inventory item via AJAX"""
    
    # Check permissions
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager', 'inventory_manager']
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            return JsonResponse({'success': False, 'error': 'Permission denied'})
    elif not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    form = AddInventoryForm(request.POST)
    
    if form.is_valid():
        try:
            with transaction.atomic():
                # Check if similar item exists (same crop, location, quality, close expiry date)
                existing_item = InventoryItem.objects.filter(
                    crop_type=form.cleaned_data['crop_type'],
                    storage_location=form.cleaned_data['storage_location'],
                    quality_grade=form.cleaned_data['quality_grade'],
                    expiry_date=form.cleaned_data['expiry_date']
                ).first()
                
                if existing_item:
                    # Update existing item
                    previous_quantity = existing_item.quantity
                    existing_item.quantity += form.cleaned_data['quantity']
                    existing_item.save()
                    
                    # Create transaction record
                    InventoryTransaction.objects.create(
                        inventory_item=existing_item,
                        user=request.user,
                        action_type='ADD',
                        quantity=form.cleaned_data['quantity'],
                        previous_quantity=previous_quantity,
                        new_quantity=existing_item.quantity,
                        notes=f"Stock added to existing batch at {existing_item.storage_location.name}"
                    )
                    
                    inventory_item = existing_item
                else:
                    # Create new inventory item
                    inventory_item = form.save(commit=False)
                    inventory_item.added_by = request.user
                    inventory_item.save()
                    
                    # Create transaction record
                    InventoryTransaction.objects.create(
                        inventory_item=inventory_item,
                        user=request.user,
                        action_type='ADD',
                        quantity=inventory_item.quantity,
                        previous_quantity=0,
                        new_quantity=inventory_item.quantity,
                        notes=f"Initial stock added to {inventory_item.storage_location.name}"
                    )
                
                return JsonResponse({
                    'success': True,
                    'message': f'Successfully added {form.cleaned_data["quantity"]}t of {inventory_item.crop_type.display_name} to inventory',
                    'stats': InventoryItem.objects.get_summary_stats()
                })
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    else:
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = field_errors[0]
        
        return JsonResponse({'success': False, 'errors': errors})


@login_required
@require_POST
def remove_inventory(request):
    """Remove inventory items via AJAX using FIFO method"""
    
    # Check permissions
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager', 'inventory_manager']
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            return JsonResponse({'success': False, 'error': 'Permission denied'})
    elif not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    form = RemoveInventoryForm(request.POST)
    
    if form.is_valid():
        try:
            with transaction.atomic():
                crop_type = form.cleaned_data['crop_type']
                storage_location = form.cleaned_data['storage_location']
                quantity_to_remove = form.cleaned_data['quantity']
                notes = form.cleaned_data.get('notes', '')
                
                # Get available inventory items (FIFO - oldest first)
                available_items = InventoryItem.objects.filter(
                    crop_type=crop_type,
                    storage_location=storage_location,
                    quantity__gt=0
                ).order_by('date_stored', 'created_at')
                
                if not available_items.exists():
                    return JsonResponse({
                        'success': False, 
                        'error': f'No inventory available for {crop_type.display_name} at {storage_location.name}'
                    })
                
                # Check total available quantity
                total_available = sum(item.quantity for item in available_items)
                if total_available < quantity_to_remove:
                    return JsonResponse({
                        'success': False,
                        'error': f'Insufficient stock. Only {total_available}t available, but {quantity_to_remove}t requested.'
                    })
                
                remaining_to_remove = quantity_to_remove
                transactions = []
                items_to_delete = []
                
                # Remove inventory using FIFO method
                for item in available_items:
                    if remaining_to_remove <= 0:
                        break
                    
                    previous_quantity = item.quantity
                    
                    if item.quantity <= remaining_to_remove:
                        # Remove entire item
                        quantity_removed = item.quantity
                        remaining_to_remove -= quantity_removed
                        item.quantity = 0
                        items_to_delete.append(item.id)
                    else:
                        # Partially remove from item
                        quantity_removed = remaining_to_remove
                        item.quantity -= remaining_to_remove
                        remaining_to_remove = 0
                    
                    item.save()
                    
                    # Create transaction record
                    transaction_obj = InventoryTransaction.objects.create(
                        inventory_item=item,
                        user=request.user,
                        action_type='REMOVE',
                        quantity=-quantity_removed,  # Negative for removal
                        previous_quantity=previous_quantity,
                        new_quantity=item.quantity,
                        notes=notes or f"Stock removed from {storage_location.name}"
                    )
                    transactions.append(transaction_obj)
                
                # Delete items with zero quantity
                if items_to_delete:
                    InventoryItem.objects.filter(id__in=items_to_delete).delete()
                
                total_removed = quantity_to_remove - remaining_to_remove
                
                return JsonResponse({
                    'success': True,
                    'message': f'Successfully removed {total_removed}t of {crop_type.display_name} from {storage_location.name}',
                    'stats': InventoryItem.objects.get_summary_stats()
                })
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    else:
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = field_errors[0]
        
        return JsonResponse({'success': False, 'errors': errors})


@login_required
def inventory_stats_api(request):
    """API endpoint for real-time inventory statistics"""
    
    # Check permissions
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager', 'inventory_manager']
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    elif not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        stats = InventoryItem.objects.get_summary_stats()
        
        # Add more detailed stats
        crop_breakdown = {}
        location_breakdown = {}
        
        inventory_items = InventoryItem.objects.select_related('crop_type', 'storage_location')
        
        for item in inventory_items:
            # Crop breakdown
            crop_name = item.crop_type.display_name
            if crop_name not in crop_breakdown:
                crop_breakdown[crop_name] = {
                    'quantity': 0,
                    'locations': set(),
                    'statuses': {'good': 0, 'expiring': 0, 'low_stock': 0, 'expired': 0}
                }
            
            crop_breakdown[crop_name]['quantity'] += float(item.quantity)
            crop_breakdown[crop_name]['locations'].add(item.storage_location.name)
            crop_breakdown[crop_name]['statuses'][item.status] += 1
            
            # Location breakdown
            location_name = item.storage_location.name
            if location_name not in location_breakdown:
                location_breakdown[location_name] = {
                    'quantity': 0,
                    'crops': set(),
                    'capacity': float(item.storage_location.capacity_tons),
                    'usage_percentage': 0
                }
            
            location_breakdown[location_name]['quantity'] += float(item.quantity)
            location_breakdown[location_name]['crops'].add(item.crop_type.display_name)
        
        # Convert sets to lists for JSON serialization
        for crop_data in crop_breakdown.values():
            crop_data['locations'] = list(crop_data['locations'])
        
        for location_data in location_breakdown.values():
            location_data['crops'] = list(location_data['crops'])
            if location_data['capacity'] > 0:
                location_data['usage_percentage'] = (location_data['quantity'] / location_data['capacity']) * 100
        
        return JsonResponse({
            'success': True,
            'stats': stats,
            'crop_breakdown': crop_breakdown,
            'location_breakdown': location_breakdown
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_crop_locations(request):
    """Get available locations for a specific crop type (for removal form)"""
    
    crop_type_id = request.GET.get('crop_type_id')
    
    if not crop_type_id:
        return JsonResponse({'locations': []})
    
    try:
        # Get locations that have this crop in stock
        locations_data = []
        
        inventory_items = InventoryItem.objects.filter(
            crop_type_id=crop_type_id,
            quantity__gt=0
        ).select_related('storage_location').values(
            'storage_location__id',
            'storage_location__name'
        ).annotate(
            available_quantity=Sum('quantity')
        )
        
        locations_data = [
            {
                'id': item['storage_location__id'],
                'name': item['storage_location__name'],
                'available_quantity': float(item['available_quantity'])
            }
            for item in inventory_items
        ]
        
        return JsonResponse({'locations': locations_data})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def inventory_history(request):
    """View for complete inventory transaction history"""
    
    # Check permissions
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager', 'inventory_manager']
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            messages.error(request, "You don't have permission to access inventory history.")
            return redirect('monitoring:dashboard')
    elif not request.user.is_superuser:
        messages.error(request, "You don't have permission to access inventory history.")
        return redirect('monitoring:dashboard')
    
    # Get all transactions with filters
    transactions = InventoryTransaction.objects.select_related(
        'user', 'inventory_item__crop_type', 'inventory_item__storage_location'
    ).order_by('-timestamp')
    
    # Apply filters if provided
    action_filter = request.GET.get('action')
    crop_filter = request.GET.get('crop')
    location_filter = request.GET.get('location')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if action_filter:
        transactions = transactions.filter(action_type=action_filter)
    
    if crop_filter:
        transactions = transactions.filter(inventory_item__crop_type__name=crop_filter)
    
    if location_filter:
        transactions = transactions.filter(inventory_item__storage_location_id=location_filter)
    
    if date_from:
        try:
            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            transactions = transactions.filter(timestamp__date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            from datetime import datetime
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            transactions = transactions.filter(timestamp__date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Pagination
    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'transactions': page_obj,
        'crop_types': CropType.objects.filter(is_active=True),
        'storage_locations': StorageLocation.objects.filter(is_active=True),
        'filters': {
            'action': action_filter,
            'crop': crop_filter,
            'location': location_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
    return render(request, 'monitoring/inventory_history.html', context)


@login_required
def export_inventory(request):
    """Export current inventory to CSV"""
    
    # Check permissions
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager', 'inventory_manager']
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    elif not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="inventory_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'Crop Type',
        'Storage Location',
        'Quantity (tons)',
        'Quality Grade',
        'Date Stored',
        'Expiry Date',
        'Days Until Expiry',
        'Status',
        'Added By',
        'Created At'
    ])
    
    # Write data
    inventory_items = InventoryItem.objects.select_related(
        'crop_type', 'storage_location', 'added_by'
    ).order_by('crop_type__display_name', 'storage_location__name', 'date_stored')
    
    for item in inventory_items:
        writer.writerow([
            item.crop_type.display_name,
            item.storage_location.name,
            float(item.quantity),
            item.get_quality_grade_display(),
            item.date_stored.strftime('%Y-%m-%d'),
            item.expiry_date.strftime('%Y-%m-%d'),
            item.days_until_expiry,
            item.status.title(),
            item.added_by.get_full_name() if item.added_by else 'Unknown',
            item.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response


@login_required
def dashboard(request):
    """Main dashboard view - add this if it doesn't exist"""
    
    # Basic dashboard context
    context = {
        'user': request.user,
        'current_date': timezone.now().date(),
    }
    
    return render(request, 'monitoring/dashboard.html', context)


# Additional utility views that might be needed

@login_required
@require_POST
def adjust_inventory(request):
    """Adjust inventory quantity (for corrections)"""
    
    # Check permissions
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager']  # More restrictive for adjustments
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            return JsonResponse({'success': False, 'error': 'Permission denied'})
    elif not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        item_id = request.POST.get('item_id')
        new_quantity = Decimal(request.POST.get('new_quantity', '0'))
        notes = request.POST.get('notes', '')
        
        inventory_item = get_object_or_404(InventoryItem, id=item_id)
        previous_quantity = inventory_item.quantity
        
        with transaction.atomic():
            inventory_item.quantity = new_quantity
            inventory_item.save()
            
            # Create transaction record
            InventoryTransaction.objects.create(
                inventory_item=inventory_item,
                user=request.user,
                action_type='ADJUST',
                quantity=new_quantity - previous_quantity,
                previous_quantity=previous_quantity,
                new_quantity=new_quantity,
                notes=notes or f"Quantity adjusted from {previous_quantity}t to {new_quantity}t"
            )
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully adjusted {inventory_item.crop_type.display_name} quantity to {new_quantity}t',
            'stats': InventoryItem.objects.get_summary_stats()
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def low_stock_alert(request):
    """Get low stock items for alerts"""
    
    # Check permissions
    user_profile = getattr(request.user, 'userprofile', None)
    allowed_roles = ['admin', 'farm_manager', 'inventory_manager']
    
    if user_profile and hasattr(user_profile, 'role'):
        if user_profile.role not in allowed_roles:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    elif not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        low_stock_items = []
        inventory_items = InventoryItem.objects.select_related('crop_type', 'storage_location')
        
        for item in inventory_items:
            if item.status == 'low_stock':
                low_stock_items.append({
                    'crop_type': item.crop_type.display_name,
                    'location': item.storage_location.name,
                    'current_quantity': float(item.quantity),
                    'threshold': float(item.crop_type.minimum_stock_threshold),
                    'expiry_date': item.expiry_date.strftime('%Y-%m-%d'),
                    'days_until_expiry': item.days_until_expiry
                })
        
        return JsonResponse({
            'success': True,
            'low_stock_items': low_stock_items,
            'count': len(low_stock_items)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ========================
# REPORTING VIEWS
# ========================

@login_required
def reports(request):
    """Main reports page – handles list, generate, and recent reports"""
    templates = ReportTemplate.objects.all()
    recent_reports = GeneratedReport.objects.order_by("-generated_at")[:5]

    if request.method == "POST":
        template_id = request.POST.get("template_id")
        from_date = request.POST.get("from_date")
        to_date = request.POST.get("to_date")
        export_format = request.POST.get("export_format", "pdf")

        if not template_id:
            messages.error(request, "Please select a report template.")
        else:
            template = get_object_or_404(ReportTemplate, id=template_id)

            # Simulate generated file (replace with real logic later)
            filename = f"{template.report_type}_{timezone.now().strftime('%Y%m%d%H%M%S')}.{export_format}"
            file_path = os.path.join("media/reports", filename)

            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write(f"Report: {template.title}\n")
                f.write(f"From: {from_date} To: {to_date}\n")
                f.write("Sample report content here...\n")

            report = GeneratedReport.objects.create(
                template=template,
                name=template.title,
                report_type=template.report_type,
                generated_by=request.user,
                from_date=from_date,
                to_date=to_date,
                export_format=export_format,
                file=file_path.replace("media/", ""),  # relative path
            )

            ReportActivityLog.objects.create(
                user=request.user,
                report=report,
                action="generate",
            )

            messages.success(request, f"{template.title} generated successfully!")

            # Refresh recent reports after generation
            recent_reports = GeneratedReport.objects.order_by("-generated_at")[:5]

    context = {
        "templates": templates,
        "recent_reports": recent_reports,
    }
    return render(request, "monitoring/reports.html", context)


@login_required
def download_report(request, report_id):
    """Download previously generated report"""
    report = get_object_or_404(GeneratedReport, id=report_id)

    file_path = os.path.join("media", str(report.file))
    if not os.path.exists(file_path):
        messages.error(request, "Report file not found.")
        return redirect("reports")

    ReportActivityLog.objects.create(
        user=request.user,
        report=report,
        action="download",
    )

    from django.http import FileResponse
    return FileResponse(open(file_path, "rb"), as_attachment=True, filename=os.path.basename(file_path))

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

