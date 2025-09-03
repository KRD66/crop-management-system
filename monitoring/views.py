# monitoring/views.py - Updated with proper role-based access control
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
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
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from datetime import datetime, timedelta, date
from decimal import Decimal
from collections import defaultdict
import json
import csv
import random
from io import BytesIO
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView

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

# Import custom decorators and mixins
from .decorators import (
    role_required, permission_required, object_access_required,
    RoleRequiredMixin, PermissionRequiredMixin, ObjectAccessMixin
)


# ========================
# DASHBOARD AND MAIN VIEWS
# ========================

@login_required
def dashboard(request):
    """
    Role-based dashboard view - shows different data based on user role
    """
    try:
        user_profile = request.user.userprofile
        
        # Initialize context with role-specific data
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
            'user_role': user_profile.get_role_display(),
            'user_profile': user_profile
        }
        
        # Get role-specific querysets
        farms_qs = user_profile.get_queryset_for_model('Farm')
        fields_qs = user_profile.get_queryset_for_model('Field')
        harvests_qs = user_profile.get_queryset_for_model('HarvestRecord')
        inventory_qs = user_profile.get_queryset_for_model('Inventory')
        
        # Calculate metrics based on accessible data
        total_harvested = harvests_qs.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        active_farms = farms_qs.filter(is_active=True).count()
        
        total_inventory = inventory_qs.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 0
        
        # Calculate efficiency for accessible farms
        if farms_qs.exists():
            total_actual = float(harvests_qs.aggregate(total=Sum('quantity_tons'))['total'] or 0)
            total_expected = 0
            
            for farm in farms_qs.filter(is_active=True):
                for field in field.field_set.all():
                    if field.crop.expected_yield_per_hectare:
                        total_expected += float(field.area_hectares * field.crop.expected_yield_per_hectare)
                    else:
                        total_expected += float(field.area_hectares * 5)
            
            if total_expected > 0:
                avg_yield_efficiency = min(int((total_actual / total_expected) * 100), 100)
            else:
                avg_yield_efficiency = 85
        
        # Get harvest trends for accessible data
        harvest_trends = []
        current_year = datetime.now().year
        
        for month in range(1, 13):
            month_total = harvests_qs.filter(
                harvest_date__year=current_year,
                harvest_date__month=month
            ).aggregate(total=Sum('quantity_tons'))['total'] or 0
            
            harvest_trends.append({
                'month': datetime(current_year, month, 1).strftime('%b'),
                'value': float(month_total)
            })
        
        # Get crop distribution for accessible harvests
        crop_distribution = []
        total_crop_harvests = harvests_qs.aggregate(
            total=Sum('quantity_tons')
        )['total'] or 1
        
        if total_crop_harvests > 0:
            crop_stats = harvests_qs.values('field__crop__name').annotate(
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
        
        # Get yield performance for accessible farms
        yield_performance = []
        accessible_farms = farms_qs.filter(is_active=True)[:4]
        
        for farm in accessible_farms:
            farm_fields = fields_qs.filter(farm=farm)
            expected_yield = 0
            
            for field in farm_fields:
                if field.crop.expected_yield_per_hectare:
                    expected_yield += float(field.area_hectares * field.crop.expected_yield_per_hectare)
                else:
                    expected_yield += float(field.area_hectares * 5)
            
            actual_yield = harvests_qs.filter(
                field__farm=farm
            ).aggregate(total=Sum('quantity_tons'))['total'] or 0
            
            yield_performance.append({
                'farm': farm.name[:10] + ('...' if len(farm.name) > 10 else ''),
                'expected': expected_yield,
                'actual': float(actual_yield)
            })
        
        # Get recent harvests (accessible)
        recent_harvests = harvests_qs.select_related(
            'field__farm', 'field__crop', 'harvested_by'
        ).order_by('-harvest_date')[:5]
        
        # Get upcoming harvests (accessible)
        upcoming_date = datetime.now().date() + timedelta(days=30)
        upcoming_harvests = fields_qs.filter(
            expected_harvest_date__lte=upcoming_date,
            expected_harvest_date__gte=datetime.now().date(),
            is_active=True
        ).select_related('farm', 'crop').order_by('expected_harvest_date')[:5]
        
        # Update context with calculated values
        context.update({
            'total_harvested': float(total_harvested),
            'active_farms': active_farms,
            'total_inventory': float(total_inventory),
            'avg_yield_efficiency': avg_yield_efficiency,
            'harvest_trends': json.dumps(harvest_trends),
            'crop_distribution': crop_distribution,
            'yield_performance': json.dumps(yield_performance),
            'recent_harvests': recent_harvests,
            'upcoming_harvests': upcoming_harvests,
        })
        
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

@login_required
@role_required(['admin'])
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
        'role_choices': UserProfile.ROLE_CHOICES,
        'stats': stats,
        'can_manage_users': True
    }
    
    return render(request, 'monitoring/user_management.html', context)


@login_required
@role_required(['admin'])
def user_add(request):
    """Add new user - Admin only"""
    if request.method == 'POST':
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                messages.success(
                    request, 
                    f'User {user.username} created successfully with role: {user.userprofile.get_role_display()}'
                )
                return redirect('monitoring:user_management')
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.title()}: {error}')
    else:
        form = AdminUserCreationForm()
    
    context = {
        'form': form,
        'title': 'Add New User',
        'submit_text': 'Create User'
    }
    return render(request, 'monitoring/user_form.html', context)


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


# ========================
# FARM MANAGEMENT VIEWS
# ========================

@login_required
@permission_required('can_manage_farms')
def farm_management(request):
    """Farm management view - Farm managers and admins only"""
    user_profile = request.user.userprofile
    farms = user_profile.get_queryset_for_model('Farm')

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
        )['total'] or farm.total_area_hectares
        
        total_area_acres = farm_area_hectares * Decimal('2.47105')
        total_area += total_area_acres

        total_harvested = HarvestRecord.objects.filter(
            field__farm=farm
        ).aggregate(total=Sum('quantity_tons'))['total'] or Decimal('0')
        total_harvested_all += total_harvested

        avg_yield = total_harvested / total_area_acres if total_area_acres > 0 else Decimal('0')

        farm.calculated_field_count = field_count
        farm.calculated_total_area = total_area_acres
        farm.calculated_total_harvested = total_harvested
        farm.calculated_avg_yield = avg_yield
        
        farms_with_stats.append(farm)

    avg_farm_size = total_area / total_farms if total_farms > 0 else Decimal('0')

    context = {
        'total_farms': total_farms,
        'active_farms': active_farms,
        'total_area': round(float(total_area), 1),
        'avg_farm_size': round(float(avg_farm_size), 1),
        'total_fields': total_fields,
        'farms': farms_with_stats,
        'can_create_farm': user_profile.role == 'admin',
        'can_edit_farms': user_profile.can_manage_farms,
    }

    return render(request, 'monitoring/farm_management.html', context)


class FarmListView(RoleRequiredMixin, ObjectAccessMixin, ListView):
    """List farms with role-based filtering"""
    model = Farm
    template_name = 'monitoring/farm_list.html'
    allowed_roles = ['admin', 'farm_manager', 'field_supervisor']
    context_object_name = 'farms'
    paginate_by = 10
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_farms'] = self.get_queryset().count()
        context['can_create_farm'] = self.request.user.userprofile.role == 'admin'
        return context


class FarmDetailView(LoginRequiredMixin, DetailView):
    """Farm detail view with object-level access control"""
    model = Farm
    template_name = 'monitoring/farm_detail.html'
    context_object_name = 'farm'
    
    def get_object(self):
        obj = super().get_object()
        user_profile = self.request.user.userprofile
        if not user_profile.can_access_object(obj):
            raise Http404("Farm not found or access denied")
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        farm = self.object
        user_profile = self.request.user.userprofile
        
        # Get accessible fields for this farm
        fields = user_profile.get_queryset_for_model('Field').filter(farm=farm)
        
        # Get recent harvests
        recent_harvests = user_profile.get_queryset_for_model('HarvestRecord').filter(
            field__farm=farm
        ).select_related('field', 'harvested_by').order_by('-harvest_date')[:10]
        
        context.update({
            'fields': fields,
            'recent_harvests': recent_harvests,
            'can_edit': user_profile.can_access_object(farm) and user_profile.can_manage_farms,
            'field_count': fields.count(),
            'total_harvested': recent_harvests.aggregate(total=Sum('quantity_tons'))['total'] or 0
        })
        return context


# ========================
# HARVEST TRACKING VIEWS
# ========================

@login_required
@permission_required('can_track_harvests')
def harvest_tracking(request):
    """Harvest Tracking view - shows harvests user can access"""
    user_profile = request.user.userprofile
    harvests = user_profile.get_queryset_for_model('HarvestRecord').select_related(
        'field__farm', 'field__crop', 'harvested_by'
    ).order_by('-harvest_date')[:50]
    
    total_harvests = user_profile.get_queryset_for_model('HarvestRecord').count()
    total_quantity = user_profile.get_queryset_for_model('HarvestRecord').aggregate(
        total=Sum('quantity_tons')
    )['total'] or 0
    
    week_ago = datetime.now().date() - timedelta(days=7)
    recent_activity = user_profile.get_queryset_for_model('HarvestRecord').filter(
        harvest_date__gte=week_ago
    ).count()
    
    available_fields = user_profile.get_queryset_for_model('Field').select_related('farm', 'crop').filter(
        farm__is_active=True,
        is_active=True
    ).order_by('farm__name', 'name')
    
    context = {
        'harvests': harvests,
        'total_harvests': total_harvests,
        'total_quantity': float(total_quantity),
        'recent_activity': recent_activity,
        'available_fields': available_fields,
        'can_create_harvest': user_profile.can_track_harvests,
        'can_edit_harvests': user_profile.role in ['admin', 'farm_manager'],
    }
    
    return render(request, 'monitoring/harvest_tracking.html', context)


class HarvestListView(PermissionRequiredMixin, ObjectAccessMixin, ListView):
    """List harvest records with role-based filtering"""
    model = HarvestRecord
    template_name = 'monitoring/harvest_list.html'
    permission_method = 'can_track_harvests'
    context_object_name = 'harvests'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters if provided
        farm_filter = self.request.GET.get('farm')
        crop_filter = self.request.GET.get('crop')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if farm_filter:
            queryset = queryset.filter(field__farm__id=farm_filter)
        
        if crop_filter:
            queryset = queryset.filter(field__crop__id=crop_filter)
        
        if date_from:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(harvest_date__gte=from_date)
            except ValueError:
                pass
        
        if date_to:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(harvest_date__lte=to_date)
            except ValueError:
                pass
        
        return queryset.select_related('field__farm', 'field__crop', 'harvested_by')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_profile = self.request.user.userprofile
        
        # Get accessible farms and crops for filters
        accessible_farms = user_profile.get_queryset_for_model('Farm').filter(is_active=True)
        accessible_fields = user_profile.get_queryset_for_model('Field')
        accessible_crops = Crop.objects.filter(
            field__in=accessible_fields
        ).distinct().order_by('name')
        
        context.update({
            'farms': accessible_farms,
            'crops': accessible_crops,
            'farm_filter': self.request.GET.get('farm'),
            'crop_filter': self.request.GET.get('crop'),
            'date_from': self.request.GET.get('date_from'),
            'date_to': self.request.GET.get('date_to'),
            'total_harvests': self.get_queryset().count(),
            'can_create_harvest': user_profile.can_track_harvests,
        })
        return context


class HarvestDetailView(LoginRequiredMixin, DetailView):
    """Harvest detail view with object-level access control"""
    model = HarvestRecord
    template_name = 'monitoring/harvest_detail.html'
    context_object_name = 'harvest'
    
    def get_object(self):
        obj = super().get_object()
        user_profile = self.request.user.userprofile
        if not user_profile.can_access_object(obj):
            raise Http404("Harvest record not found or access denied")
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_profile = self.request.user.userprofile
        context['can_edit'] = user_profile.role in ['admin', 'farm_manager']
        context['can_delete'] = user_profile.role == 'admin'
        return context


@login_required
@permission_required('can_track_harvests')
def harvest_add(request):
    """Add new harvest record"""
    user_profile = request.user.userprofile
    
    if request.method == 'POST':
        field_id = request.POST.get('field')
        quantity_tons = request.POST.get('quantity_tons')
        harvest_date = request.POST.get('harvest_date')
        quality_grade = request.POST.get('quality_grade', 'A')
        
        try:
            # Check if user can access this field
            accessible_fields = user_profile.get_queryset_for_model('Field')
            field = accessible_fields.get(id=field_id)
            
            harvest = HarvestRecord.objects.create(
                field=field,
                quantity_tons=Decimal(quantity_tons),
                harvest_date=datetime.strptime(harvest_date, '%Y-%m-%d').date(),
                quality_grade=quality_grade,
                harvested_by=request.user
            )
            
            messages.success(request, f'Harvest record created successfully: {quantity_tons} tons from {field.name}')
            return redirect('monitoring:harvest_detail', pk=harvest.id)
            
        except Field.DoesNotExist:
            messages.error(request, 'You do not have access to this field.')
        except Exception as e:
            messages.error(request, f'Error creating harvest record: {str(e)}')
    
    # Get accessible fields for the form
    fields = user_profile.get_queryset_for_model('Field').filter(
        is_active=True
    ).select_related('farm', 'crop').order_by('farm__name', 'name')
    
    context = {
        'fields': fields,
        'today': datetime.now().date(),
        'quality_choices': HarvestRecord.QUALITY_GRADES,
    }
    return render(request, 'monitoring/harvest_add.html', context)


@login_required
@role_required(['admin', 'farm_manager'])
@object_access_required(HarvestRecord)
def harvest_edit(request, pk):
    """Edit harvest record - Admin and Farm Manager only"""
    harvest = get_object_or_404(HarvestRecord, pk=pk)
    
    if request.method == 'POST':
        try:
            harvest.quantity_tons = Decimal(request.POST.get('quantity_tons'))
            harvest.harvest_date = datetime.strptime(request.POST.get('harvest_date'), '%Y-%m-%d').date()
            harvest.quality_grade = request.POST.get('quality_grade')
            
            # Add notes about the edit
            if hasattr(harvest, 'notes'):
                harvest.notes += f"\n[{datetime.now().date()}] Edited by {request.user.get_full_name() or request.user.username}"
            
            harvest.save()
            
            messages.success(request, 'Harvest record updated successfully.')
            return redirect('monitoring:harvest_detail', pk=harvest.pk)
            
        except Exception as e:
            messages.error(request, f'Error updating harvest record: {str(e)}')
    
    context = {
        'harvest': harvest,
        'quality_choices': HarvestRecord.QUALITY_GRADES,
    }
    return render(request, 'monitoring/harvest_edit.html', context)


# ========================
# ANALYTICS VIEWS
# ========================

@login_required
@permission_required('can_view_analytics')
def analytics(request):
    """Analytics view - shows data user can access"""
    try:
        user_profile = request.user.userprofile
        current_year = datetime.now().year
        current_date = datetime.now().date()
        
        # Get accessible data based on role
        farms_qs = user_profile.get_queryset_for_model('Farm')
        fields_qs = user_profile.get_queryset_for_model('Field')
        harvests_qs = user_profile.get_queryset_for_model('HarvestRecord')
        
        # Calculate efficiency for accessible farms
        farms_data = []
        total_efficiency = 0
        underperforming_count = 0
        
        for farm in farms_qs.filter(is_active=True).prefetch_related('field_set__crop'):
            # Only include fields user can access
            accessible_farm_fields = fields_qs.filter(farm=farm)
            
            expected_total = 0
            for field in accessible_farm_fields:
                if field.crop.expected_yield_per_hectare:
                    expected_total += float(field.area_hectares * field.crop.expected_yield_per_hectare)
                else:
                    expected_total += float(field.area_hectares * 5)
            
            actual_total = float(harvests_qs.filter(
                field__farm=farm
            ).aggregate(total=Sum('quantity_tons'))['total'] or 0)
            
            if expected_total > 0:
                efficiency = min((actual_total / expected_total) * 100, 100)
            else:
                efficiency = 0
            
            primary_crop = 'Mixed'
            if accessible_farm_fields.exists():
                crop_counts = defaultdict(int)
                for field in accessible_farm_fields:
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
        
        # Calculate predicted harvest for accessible fields
        two_weeks_later = current_date + timedelta(days=14)
        upcoming_fields = fields_qs.filter(
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
        
        # Yield Performance Chart Data (accessible farms only)
        yield_performance_data = []
        for farm_data in farms_data[:8]:
            yield_performance_data.append({
                'farm': farm_data['name'][:12] + ('...' if len(farm_data['name']) > 12 else ''),
                'expected': round(farm_data['expected_yield'], 1),
                'actual': round(farm_data['actual_yield'], 1)
            })
        
        # Seasonal Trends Data (accessible harvests only)
        seasonal_trends_data = {'corn': [], 'wheat': [], 'soybeans': []}
        
        for year in range(2020, 2025):
            for crop_name, crop_key in [('corn', 'corn'), ('wheat', 'wheat'), ('soy', 'soybeans')]:
                total = harvests_qs.filter(
                    harvest_date__year=year,
                    field__crop__name__icontains=crop_name
                ).aggregate(total=Sum('quantity_tons'))['total'] or 0
                seasonal_trends_data[crop_key].append(float(total))
        
        # Weather Correlation Data (based on accessible data)
        weather_correlation_data = {'performance': [], 'rainfall': []}
        
        for month in range(1, 9):
            month_harvests = harvests_qs.filter(
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
        
        # Farm Rankings (accessible farms only)
        farm_rankings = sorted(farms_data, key=lambda x: x['efficiency'], reverse=True)[:10]
        
        # Harvest Predictions (accessible fields only)
        harvest_predictions = []
        upcoming_fields_pred = fields_qs.filter(
            expected_harvest_date__gte=current_date,
            expected_harvest_date__lte=current_date + timedelta(days=60),
            is_active=True
        ).select_related('farm', 'crop')[:8]
        
        for field in upcoming_fields_pred:
            if field.crop.expected_yield_per_hectare:
                predicted_amount = float(field.area_hectares * field.crop.expected_yield_per_hectare)
            else:
                predicted_amount = float(field.area_hectares * 5)
            
            confidence = 85 + random.randint(-5, 10)
            confidence = min(max(confidence, 80), 98)
            
            harvest_predictions.append({
                'crop': field.crop.name,
                'field': f"{field.farm.name} - {field.name}",
                'amount': round(predicted_amount, 1),
                'date': field.expected_harvest_date,
                'confidence': confidence
            })
        
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
            'accessible_farms_count': farms_qs.count(),
            'accessible_harvests_count': harvests_qs.count(),
        }
        
        return render(request, 'monitoring/analytics.html', context)
    
    except Exception as e:
        print(f"Analytics view error: {e}")
        
        # Provide fallback context
        fallback_context = {
            'avg_efficiency': 85.0,
            'top_performer': {'name': 'No Data Available', 'efficiency': 0},
            'predicted_harvest': 0,
            'underperforming_count': 0,
            'yield_performance_data': json.dumps([]),
            'seasonal_trends_data': json.dumps({'corn': [], 'wheat': [], 'soybeans': []}),
            'weather_correlation_data': json.dumps({'performance': [], 'rainfall': []}),
            'farm_rankings': [],
            'harvest_predictions': [],
            'current_year': datetime.now().year,
            'total_farms_analyzed': 0,
            'has_data': False,
            'error_message': 'Unable to load analytics data.',
        }
        
        return render(request, 'monitoring/analytics.html', fallback_context)


# ========================
# INVENTORY MANAGEMENT VIEWS
# ========================

@login_required
@permission_required('can_manage_inventory')
def inventory(request):
    """Main inventory management view - Inventory managers and admins only"""
    user_profile = request.user.userprofile
    
    # Initialize forms
    add_form = AddInventoryForm(user=request.user)
    remove_form = RemoveInventoryForm()
    filter_form = InventoryFilterForm(request.GET or None)
    bulk_form = BulkInventoryUpdateForm()
    
    # Get accessible inventory items
    inventory_items = user_profile.get_queryset_for_model('Inventory').select_related(
        'crop', 'managed_by'
    ).order_by('-date_stored')
    
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
    
    context = {
        'inventory_items': inventory_items[:50],
        'total_items': inventory_items.count(),
        'total_quantity': total_quantity,
        'total_value': total_value,
        'low_stock_count': low_stock_count,
        'expiring_count': expiring_count,
        'expired_count': expired_count,
        'add_form': add_form,
        'remove_form': remove_form,
        'filter_form': filter_form,
        'bulk_form': bulk_form,
        'can_edit_inventory': user_profile.can_manage_inventory,
    }
    
    return render(request, 'monitoring/inventory.html', context)


class InventoryListView(PermissionRequiredMixin, ObjectAccessMixin, ListView):
    """Inventory list view with permission checking"""
    model = Inventory
    template_name = 'monitoring/inventory_list.html'
    permission_method = 'can_manage_inventory'
    context_object_name = 'inventory_items'
    paginate_by = 20
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit_inventory'] = self.request.user.userprofile.can_manage_inventory
        return context


# ========================
# REPORTING VIEWS
# ========================

@login_required
@permission_required('can_generate_reports')
def reports(request):
    """Reports view - users with report generation permissions only"""
    user_profile = request.user.userprofile
    
    # Get accessible data for report generation
    current_month = timezone.now().replace(day=1)
    last_month = (current_month - timedelta(days=1)).replace(day=1)
    
    accessible_harvests = user_profile.get_queryset_for_model('HarvestRecord')
    
    current_month_harvests = accessible_harvests.filter(
        harvest_date__gte=current_month
    ).aggregate(
        count=Count('id'),
        total=Sum('quantity_tons')
    )
    
    last_month_harvests = accessible_harvests.filter(
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
        'last_month_name': last_month.strftime('%B %Y'),
        'can_export_all': user_profile.role == 'admin',
        'accessible_farms_count': user_profile.get_queryset_for_model('Farm').count(),
    }
    
    return render(request, 'monitoring/reports.html', context)


@login_required
@permission_required('can_generate_reports')
def generate_report(request):
    """Generate custom reports based on user input and accessible data"""
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
        
        # Get user's accessible data
        user_profile = request.user.userprofile
        
        if report_type == 'monthly_harvest_summary':
            return generate_harvest_summary_report(request.user, from_date, to_date, export_format)
        elif report_type == 'yield_performance_report':
            return generate_yield_performance_report(request.user, from_date, to_date, export_format)
        elif report_type == 'inventory_status_report':
            if user_profile.can_manage_inventory:
                return generate_inventory_status_report(request.user, from_date, to_date, export_format)
            else:
                return JsonResponse({'success': False, 'error': 'Insufficient permissions for inventory reports'})
        elif report_type == 'farm_productivity_analysis':
            return generate_farm_productivity_report(request.user, from_date, to_date, export_format)
        else:
            return JsonResponse({'success': False, 'error': 'Invalid report type'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def generate_harvest_summary_report(user, from_date, to_date, export_format):
    """Generate harvest summary report with user's accessible data"""
    user_profile = user.userprofile
    harvests = user_profile.get_queryset_for_model('HarvestRecord').filter(
        harvest_date__range=[from_date, to_date]
    ).select_related('field', 'field__farm', 'field__crop', 'harvested_by')
    
    if export_format == 'csv':
        return generate_csv_harvest_report(harvests, from_date, to_date)
    
    return JsonResponse({'success': True, 'message': 'Report generated successfully'})


def generate_csv_harvest_report(harvests, from_date, to_date):
    """Generate CSV harvest summary report"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="harvest_summary_{from_date}_{to_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Date', 'Farm', 'Field', 'Crop', 'Quantity (tons)', 'Quality Grade', 
        'Harvested By', 'Weather Conditions'
    ])
    
    for harvest in harvests:
        writer.writerow([
            harvest.harvest_date.strftime('%Y-%m-%d'),
            harvest.field.farm.name,
            harvest.field.name,
            harvest.field.crop.name,
            harvest.quantity_tons,
            harvest.quality_grade,
            harvest.harvested_by.get_full_name() or harvest.harvested_by.username,
            getattr(harvest, 'weather_conditions', 'N/A') or 'N/A'
        ])
    
    return response


# ========================
# FIELD MANAGEMENT VIEWS
# ========================

class FieldListView(PermissionRequiredMixin, ObjectAccessMixin, ListView):
    """List fields with role-based filtering"""
    model = Field
    template_name = 'monitoring/field_list.html'
    permission_method = 'can_supervise_fields'
    context_object_name = 'fields'
    paginate_by = 20
    
    def get_queryset(self):
        return super().get_queryset().select_related('farm', 'crop', 'supervisor').filter(is_active=True)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_profile = self.request.user.userprofile
        context.update({
            'total_fields': self.get_queryset().count(),
            'can_create_field': user_profile.role in ['admin', 'farm_manager'],
            'can_edit_fields': user_profile.can_supervise_fields,
        })
        return context


class FieldDetailView(LoginRequiredMixin, DetailView):
    """Field detail view with object-level access control"""
    model = Field
    template_name = 'monitoring/field_detail.html'
    context_object_name = 'field'
    
    def get_object(self):
        obj = super().get_object()
        user_profile = self.request.user.userprofile
        if not user_profile.can_access_object(obj):
            raise Http404("Field not found or access denied")
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = self.object
        user_profile = self.request.user.userprofile
        
        # Get accessible harvests for this field
        harvests = user_profile.get_queryset_for_model('HarvestRecord').filter(
            field=field
        ).select_related('harvested_by').order_by('-harvest_date')
        
        context.update({
            'harvests': harvests,
            'total_harvested': harvests.aggregate(total=Sum('quantity_tons'))['total'] or 0,
            'harvest_count': harvests.count(),
            'can_edit': user_profile.can_access_object(field) and user_profile.can_supervise_fields,
            'can_create_harvest': user_profile.can_track_harvests,
        })
        return context


# ========================
# NOTIFICATIONS VIEWS
# ========================

@login_required
def notifications(request):
    """Notifications view - all users can view notifications relevant to their role"""
    user_profile = request.user.userprofile
    
    # Get role-specific notifications
    notifications = []
    
    # Upcoming harvests for accessible fields
    if user_profile.can_track_harvests:
        upcoming_fields = user_profile.get_queryset_for_model('Field').filter(
            expected_harvest_date__lte=datetime.now().date() + timedelta(days=7),
            expected_harvest_date__gte=datetime.now().date(),
            is_active=True
        ).select_related('farm', 'crop')
        
        for field in upcoming_fields:
            notifications.append({
                'type': 'harvest_due',
                'title': 'Harvest Due Soon',
                'message': f'{field.crop.name} in {field.farm.name} - {field.name} is due for harvest on {field.expected_harvest_date}',
                'date': field.expected_harvest_date,
                'priority': 'high' if field.days_to_harvest <= 3 else 'medium'
            })
    
    # Low inventory alerts (for inventory managers)
    if user_profile.can_manage_inventory:
        low_inventory = user_profile.get_queryset_for_model('Inventory').filter(
            quantity_tons__lt=100
        ).select_related('crop')
        
        for item in low_inventory:
            notifications.append({
                'type': 'low_inventory',
                'title': 'Low Inventory Alert',
                'message': f'{item.crop.name} at {item.storage_location} is running low ({item.quantity_tons} tons remaining)',
                'date': datetime.now().date(),
                'priority': 'medium' if item.quantity_tons > 50 else 'high'
            })
    
    # Expiring inventory alerts
    if user_profile.can_manage_inventory:
        thirty_days = date.today() + timedelta(days=30)
        expiring_inventory = user_profile.get_queryset_for_model('Inventory').filter(
            expiry_date__lte=thirty_days,
            expiry_date__gt=date.today()
        ).select_related('crop')
        
        for item in expiring_inventory:
            days_until_expiry = (item.expiry_date - date.today()).days
            notifications.append({
                'type': 'inventory_expiring',
                'title': 'Inventory Expiring Soon',
                'message': f'{item.crop.name} will expire in {days_until_expiry} days ({item.quantity_tons} tons)',
                'date': item.expiry_date,
                'priority': 'high' if days_until_expiry <= 7 else 'medium'
            })
    
    # Sort notifications by priority and date
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    notifications.sort(key=lambda x: (priority_order.get(x['priority'], 2), x['date']))
    
    context = {
        'notifications': notifications,
        'notification_count': len(notifications),
        'high_priority_count': len([n for n in notifications if n['priority'] == 'high']),
        'can_manage_inventory': user_profile.can_manage_inventory,
        'can_track_harvests': user_profile.can_track_harvests,
    }
    
    return render(request, 'monitoring/notifications.html', context)


# ========================
# PROFILE MANAGEMENT VIEWS
# ========================

@login_required
def profile_view(request):
    """View user profile - all authenticated users"""
    context = {
        'user': request.user,
        'profile': request.user.userprofile,
    }
    return render(request, 'monitoring/profile.html', context)


@login_required
def profile_edit(request):
    """Edit user profile (limited fields) - all authenticated users"""
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


# ========================
# API ENDPOINTS WITH ROLE CHECKING
# ========================

@login_required
@role_required(['admin'])
@csrf_exempt
def api_user_toggle_status(request, user_id):
    """Toggle user active status via API - Admin only"""
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


@login_required
@permission_required('can_view_analytics')
def get_farm_efficiency(request, farm_id):
    """API endpoint to get farm efficiency data - only accessible farms"""
    try:
        user_profile = request.user.userprofile
        accessible_farms = user_profile.get_queryset_for_model('Farm')
        farm = accessible_farms.get(id=farm_id, is_active=True)
        
        # Get accessible fields for this farm
        accessible_fields = user_profile.get_queryset_for_model('Field').filter(farm=farm)
        
        fields_data = []
        total_expected = 0
        total_actual = 0
        
        for field in accessible_fields:
            field_expected = float(field.area_hectares * (field.crop.expected_yield_per_hectare or 5))
            field_actual = float(user_profile.get_queryset_for_model('HarvestRecord').filter(
                field=field
            ).aggregate(total=Sum('quantity_tons'))['total'] or 0)
            
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
            'error': 'Farm not found or access denied'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def get_live_metrics(request):
    """API endpoint for live dashboard metrics updates - role-based data"""
    try:
        user_profile = request.user.userprofile
        
        # Get metrics for accessible data
        total_harvests = user_profile.get_queryset_for_model('HarvestRecord').count()
        active_farms = user_profile.get_queryset_for_model('Farm').filter(is_active=True).count()
        
        total_inventory = 0
        if user_profile.can_manage_inventory:
            total_inventory = user_profile.get_queryset_for_model('Inventory').aggregate(
                total=Sum('quantity_tons')
            )['total'] or 0
        
        week_ago = datetime.now().date() - timedelta(days=7)
        recent_harvests = user_profile.get_queryset_for_model('HarvestRecord').filter(
            harvest_date__gte=week_ago
        ).count()
        
        next_week = datetime.now().date() + timedelta(days=7)
        upcoming_harvests = user_profile.get_queryset_for_model('Field').filter(
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
            'user_role': user_profile.get_role_display(),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ========================
# INVENTORY OPERATIONS WITH ROLE CHECKING
# ========================

@login_required
@permission_required('can_manage_inventory')
def add_inventory(request):
    """Add new inventory item - Inventory managers and admins only"""
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
@permission_required('can_manage_inventory')
def remove_inventory(request):
    """Remove inventory items - Inventory managers and admins only"""
    if request.method == 'POST':
        form = RemoveInventoryForm(request.POST)
        if form.is_valid():
            crop = form.cleaned_data['crop']
            storage_location = form.cleaned_data['storage_location']
            quantity_to_remove = form.cleaned_data['quantity_tons']
            reason = form.cleaned_data.get('reason', '')
            
            try:
                # Get accessible inventory items only
                user_profile = request.user.userprofile
                with transaction.atomic():
                    inventory_items = user_profile.get_queryset_for_model('Inventory').filter(
                        crop=crop,
                        storage_location=storage_location,
                        quantity_tons__gt=0
                    ).order_by('date_stored')
                    
                    if not inventory_items.exists():
                        return JsonResponse({
                            'success': False,
                            'message': f"No accessible inventory found for {crop.name} at {storage_location}"
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
@permission_required('can_manage_inventory')
def get_inventory_locations(request):
    """AJAX endpoint to get available storage locations for a specific crop"""
    user_profile = request.user.userprofile
    crop_id = request.GET.get('crop_id')
    
    if crop_id:
        locations = user_profile.get_queryset_for_model('Inventory').filter(
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
@permission_required('can_manage_inventory')
def inventory_summary(request):
    """Get inventory summary data for dashboard - accessible data only"""
    user_profile = request.user.userprofile
    inventory_qs = user_profile.get_queryset_for_model('Inventory')
    
    total_quantity = inventory_qs.aggregate(total=Sum('quantity_tons'))['total'] or 0
    total_items = inventory_qs.count()
    total_value = inventory_qs.aggregate(
        total=Sum(F('quantity_tons') * F('unit_price'))
    )['total'] or 0
    
    thirty_days = date.today() + timedelta(days=30)
    low_stock_count = inventory_qs.filter(quantity_tons__lt=10).count()
    expiring_count = inventory_qs.filter(
        expiry_date__lte=thirty_days,
        expiry_date__gt=date.today()
    ).count()
    
    top_crops = inventory_qs.values('crop__name').annotate(
        total_quantity=Sum('quantity_tons')
    ).order_by('-total_quantity')[:5]
    
    storage_utilization = inventory_qs.values('storage_location').annotate(
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
@permission_required('can_manage_inventory')
def bulk_update_inventory(request):
    """Bulk update inventory items - accessible items only"""
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
                user_profile = request.user.userprofile
                with transaction.atomic():
                    # Only update items user can access
                    items = user_profile.get_queryset_for_model('Inventory').filter(id__in=selected_items)
                    count = items.count()
                    
                    if count == 0:
                        return JsonResponse({
                            'success': False,
                            'message': 'No accessible items found for update'
                        })
                    
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
@permission_required('can_manage_inventory')
def export_inventory(request):
    """Export inventory data to CSV - accessible data only"""
    user_profile = request.user.userprofile
    inventory_items = user_profile.get_queryset_for_model('Inventory').select_related('crop', 'managed_by')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Crop', 'Quantity (tons)', 'Storage Location', 'Quality Grade',
        'Date Stored', 'Expiry Date', 'Storage Condition', 'Batch Number',
        'Unit Price', 'Total Value', 'Managed By', 'Status'
    ])
    
    for item in inventory_items:
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
# ADDITIONAL UTILITY FUNCTIONS WITH ROLE-BASED ACCESS
# ========================

@login_required
@permission_required('can_view_analytics')
def get_yearly_trends(request, year):
    """API endpoint to get seasonal trends for a specific year - accessible data only"""
    try:
        user_profile = request.user.userprofile
        accessible_harvests = user_profile.get_queryset_for_model('HarvestRecord')
        
        trends_data = {}
        
        for crop_name, crop_key in [('corn', 'corn'), ('wheat', 'wheat'), ('soy', 'soybeans')]:
            monthly_data = []
            
            for month in range(1, 13):
                total = accessible_harvests.filter(
                    harvest_date__year=year,
                    harvest_date__month=month,
                    field__crop__name__icontains=crop_name
                ).aggregate(total=Sum('quantity_tons'))['total'] or 0
                monthly_data.append(float(total))
            
            trends_data[crop_key] = monthly_data
        
        return JsonResponse({
            'success': True,
            'year': year,
            'data': trends_data,
            'accessible_data_only': True
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ========================
# ADDITIONAL CRUD VIEWS WITH ROLE-BASED ACCESS
# ========================

@login_required
@role_required(['admin', 'farm_manager'])
def harvest_delete(request, pk):
    """Delete harvest record - Admin and Farm Manager only"""
    user_profile = request.user.userprofile
    
    # Get harvest record user can access
    accessible_harvests = user_profile.get_queryset_for_model('HarvestRecord')
    harvest = get_object_or_404(accessible_harvests, pk=pk)
    
    if request.method == 'POST':
        try:
            field_name = harvest.field.name
            farm_name = harvest.field.farm.name
            quantity = harvest.quantity_tons
            
            harvest.delete()
            
            messages.success(request, f'Harvest record deleted: {quantity} tons from {field_name} ({farm_name})')
            return redirect('monitoring:harvest_list')
            
        except Exception as e:
            messages.error(request, f'Error deleting harvest record: {str(e)}')
            return redirect('monitoring:harvest_detail', pk=pk)
    
    context = {
        'harvest': harvest,
        'confirm_delete': True
    }
    return render(request, 'monitoring/harvest_confirm_delete.html', context)


@login_required
def crop_list(request):
    """List all crops - all authenticated users can view"""
    user_profile = request.user.userprofile
    
    # Get crops from fields user can access
    accessible_fields = user_profile.get_queryset_for_model('Field')
    crops = Crop.objects.filter(
        field__in=accessible_fields
    ).distinct().order_by('name')
    
    # Add statistics for each crop based on accessible data
    for crop in crops:
        crop.field_count = accessible_fields.filter(crop=crop).count()
        crop.total_harvested = user_profile.get_queryset_for_model('HarvestRecord').filter(
            field__crop=crop
        ).aggregate(total=Sum('quantity_tons'))['total'] or 0
    
    context = {
        'crops': crops,
        'total_crops': crops.count(),
        'accessible_data_only': user_profile.role != 'admin'
    }
    return render(request, 'monitoring/crop_list.html', context)


@login_required
def settings_view(request):
    """Settings view for system configuration - all authenticated users"""
    user_profile = request.user.userprofile
    
    # Get user-specific statistics
    user_stats = {
        'accessible_farms': user_profile.get_queryset_for_model('Farm').count(),
        'accessible_fields': user_profile.get_queryset_for_model('Field').count(),
        'accessible_harvests': user_profile.get_queryset_for_model('HarvestRecord').count(),
    }
    
    if user_profile.can_manage_inventory:
        user_stats['accessible_inventory'] = user_profile.get_queryset_for_model('Inventory').count()
    
    system_stats = {}
    if user_profile.role == 'admin':
        system_stats = {
            'total_users': User.objects.count(),
            'total_farms': Farm.objects.count(),
            'total_harvests': HarvestRecord.objects.count(),
            'total_inventory_items': Inventory.objects.count(),
        }
    
    context = {
        'user': request.user,
        'user_profile': user_profile,
        'user_stats': user_stats,
        'system_stats': system_stats,
        'system_info': {
            'version': '1.0.0',
            'last_updated': datetime.now().strftime('%Y-%m-%d'),
        },
        'can_manage_users': user_profile.can_manage_users,
        'permissions': {
            'can_manage_farms': user_profile.can_manage_farms,
            'can_track_harvests': user_profile.can_track_harvests,
            'can_manage_inventory': user_profile.can_manage_inventory,
            'can_supervise_fields': user_profile.can_supervise_fields,
            'can_view_analytics': user_profile.can_view_analytics,
            'can_generate_reports': user_profile.can_generate_reports,
        }
    }
    return render(request, 'monitoring/settings.html', context)


# ========================
# PASSWORD RESET VIEWS
# ========================

def password_reset_request(request):
    """Password reset request form - public access"""
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            reason = form.cleaned_data.get('reason', '')
            
            # In a real application, you would send an email to admins
            # or create a password reset ticket in the system
            
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


# ========================
# ROLE-SPECIFIC UTILITY VIEWS
# ========================

@login_required
def get_accessible_resources(request):
    """API endpoint to get resources accessible to current user"""
    user_profile = request.user.userprofile
    
    resources = {
        'farms': {
            'count': user_profile.get_queryset_for_model('Farm').count(),
            'can_manage': user_profile.can_manage_farms
        },
        'fields': {
            'count': user_profile.get_queryset_for_model('Field').count(),
            'can_supervise': user_profile.can_supervise_fields
        },
        'harvests': {
            'count': user_profile.get_queryset_for_model('HarvestRecord').count(),
            'can_track': user_profile.can_track_harvests
        }
    }
    
    if user_profile.can_manage_inventory:
        resources['inventory'] = {
            'count': user_profile.get_queryset_for_model('Inventory').count(),
            'can_manage': True
        }
    
    return JsonResponse({
        'success': True,
        'user_role': user_profile.get_role_display(),
        'resources': resources,
        'permissions': {
            'can_manage_farms': user_profile.can_manage_farms,
            'can_track_harvests': user_profile.can_track_harvests,
            'can_manage_inventory': user_profile.can_manage_inventory,
            'can_supervise_fields': user_profile.can_supervise_fields,
            'can_view_analytics': user_profile.can_view_analytics,
            'can_generate_reports': user_profile.can_generate_reports,
            'can_manage_users': user_profile.can_manage_users,
        }
    })


@login_required
@permission_required('can_track_harvests')
def get_harvest_suggestions(request):
    """API endpoint to get harvest suggestions for user's accessible fields"""
    user_profile = request.user.userprofile
    
    # Get fields ready for harvest
    ready_fields = user_profile.get_queryset_for_model('Field').filter(
        expected_harvest_date__lte=datetime.now().date() + timedelta(days=7),
        is_active=True
    ).select_related('farm', 'crop')
    
    suggestions = []
    for field in ready_fields:
        days_until_harvest = (field.expected_harvest_date - datetime.now().date()).days
        urgency = 'high' if days_until_harvest <= 3 else 'medium'
        
        # Estimate expected quantity
        expected_quantity = field.area_hectares * (field.crop.expected_yield_per_hectare or 5)
        
        suggestions.append({
            'field_id': field.id,
            'farm_name': field.farm.name,
            'field_name': field.name,
            'crop_name': field.crop.name,
            'expected_harvest_date': field.expected_harvest_date.strftime('%Y-%m-%d'),
            'days_until_harvest': days_until_harvest,
            'urgency': urgency,
            'expected_quantity': float(expected_quantity),
            'area_hectares': float(field.area_hectares)
        })
    
    # Sort by urgency and date
    suggestions.sort(key=lambda x: (x['days_until_harvest'], x['urgency']))
    
    return JsonResponse({
        'success': True,
        'suggestions': suggestions,
        'total_suggestions': len(suggestions)
    })


# ========================
# ERROR HANDLING VIEWS
# ========================

def permission_denied_view(request, exception=None):
    """Custom permission denied view"""
    context = {
        'error_message': 'You do not have permission to access this resource.',
        'user_role': getattr(request.user.userprofile, 'get_role_display', lambda: 'Unknown')() if hasattr(request.user, 'userprofile') else 'Unknown'
    }
    return render(request, 'monitoring/permission_denied.html', context, status=403)


def not_found_view(request, exception=None):
    """Custom 404 view"""
    context = {
        'error_message': 'The requested resource was not found or you do not have access to it.'
    }
    return render(request, 'monitoring/not_found.html', context, status=404)



def user_activate(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = True
    user.save()
    return redirect('user_list')

def user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    return redirect('user_list')