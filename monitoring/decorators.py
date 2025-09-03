# decorators.py
from functools import wraps
from django.http import Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView
from django.db.models import Sum, Count, Q, F
from django.db import models
from django.utils import timezone
from datetime import datetime, date, timedelta
from collections import defaultdict
import json


def role_required(allowed_roles):
    """Decorator to restrict view access based on user roles"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                user_profile = request.user.userprofile
                if user_profile.role and user_profile.role in allowed_roles:
                    return view_func(request, *args, **kwargs)
                else:
                    messages.error(request, "You don't have permission to access this page.")
                    return redirect('monitoring:dashboard')
            except Exception:
                messages.error(request, "Please contact admin to assign you a role.")
                return redirect('monitoring:dashboard')
        return wrapper
    return decorator


def permission_required(permission_method):
    """Decorator to check specific permissions using UserProfile methods"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                user_profile = request.user.userprofile
                if hasattr(user_profile, permission_method) and getattr(user_profile, permission_method):
                    return view_func(request, *args, **kwargs)
                else:
                    messages.error(request, "You don't have permission to perform this action.")
                    return redirect('monitoring:dashboard')
            except Exception:
                messages.error(request, "Please contact admin to assign you a role.")
                return redirect('monitoring:dashboard')
        return wrapper
    return decorator


def object_access_required(model_class):
    """Decorator to check if user can access a specific object"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            try:
                user_profile = request.user.userprofile
                # Get object ID from URL kwargs
                obj_id = kwargs.get('pk') or kwargs.get('id')
                if obj_id:
                    try:
                        obj = model_class.objects.get(id=obj_id)
                        if user_profile.can_access_object(obj):
                            return view_func(request, *args, **kwargs)
                        else:
                            raise PermissionDenied("You don't have access to this resource.")
                    except model_class.DoesNotExist:
                        raise Http404(f"{model_class.__name__} not found")
                else:
                    return view_func(request, *args, **kwargs)
            except Exception as e:
                if isinstance(e, (Http404, PermissionDenied)):
                    raise
                messages.error(request, "Access denied.")
                return redirect('monitoring:dashboard')
        return wrapper
    return decorator


class RoleRequiredMixin(LoginRequiredMixin):
    """Mixin to require specific roles for class-based views"""
    allowed_roles = []
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        try:
            user_profile = request.user.userprofile
            if not user_profile.role or user_profile.role not in self.allowed_roles:
                messages.error(request, "You don't have permission to access this page.")
                return redirect('monitoring:dashboard')
        except Exception:
            messages.error(request, "Please contact admin to assign you a role.")
            return redirect('monitoring:dashboard')
        
        return super().dispatch(request, *args, **kwargs)


class PermissionRequiredMixin(LoginRequiredMixin):
    """Mixin to check specific permissions"""
    permission_method = None
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        try:
            user_profile = request.user.userprofile
            if not hasattr(user_profile, self.permission_method) or not getattr(user_profile, self.permission_method):
                messages.error(request, "You don't have permission to access this page.")
                return redirect('monitoring:dashboard')
        except Exception:
            messages.error(request, "Please contact admin to assign you a role.")
            return redirect('monitoring:dashboard')
        
        return super().dispatch(request, *args, **kwargs)


class ObjectAccessMixin:
    """Mixin to filter querysets based on user permissions"""
    
    def get_queryset(self):
        if hasattr(self, 'model') and self.model:
            user_profile = self.request.user.userprofile
            return user_profile.get_queryset_for_model(self.model.__name__)
        return super().get_queryset()


# Utility functions for role-based operations
def get_filtered_queryset(user, model_name):
    """Get filtered queryset based on user permissions"""
    try:
        user_profile = user.userprofile
        return user_profile.get_queryset_for_model(model_name)
    except:
        from django.apps import apps
        return apps.get_model('monitoring', model_name).objects.none()


def user_can_access_object(user, obj):
    """Check if user can access a specific object"""
    try:
        return user.userprofile.can_access_object(obj)
    except:
        return False


def get_dashboard_stats(user):
    """Get dashboard statistics based on user role"""
    try:
        user_profile = user.userprofile
        stats = {}
        
        if user_profile.can_view_analytics:
            # Get harvest data user can see
            harvest_qs = user_profile.get_queryset_for_model('HarvestRecord')
            stats['total_harvested'] = harvest_qs.aggregate(
                total=Sum('quantity_tons')
            )['total'] or 0
        
        if user_profile.can_manage_farms:
            # Get farm data user can manage
            farm_qs = user_profile.get_queryset_for_model('Farm')
            stats['active_farms'] = farm_qs.filter(is_active=True).count()
        
        if user_profile.can_manage_inventory:
            # Get inventory data
            inventory_qs = user_profile.get_queryset_for_model('Inventory')
            stats['inventory_count'] = inventory_qs.count()
            stats['total_inventory_value'] = sum(
                float(item.total_value or 0) for item in inventory_qs
            )
        
        return stats
    except:
        return {}


# Context processor for user role information
def user_role_context(request):
    """Add user role information to all template contexts"""
    context = {}
    if request.user.is_authenticated:
        try:
            user_profile = request.user.userprofile
            context.update({
                'user_role': user_profile,
                'user_role_display': user_profile.get_role_display(),
                'menu_items': user_profile.get_accessible_menu_items(),
                # Permission flags for templates
                'can_manage_farms': user_profile.can_manage_farms,
                'can_track_harvests': user_profile.can_track_harvests,
                'can_manage_inventory': user_profile.can_manage_inventory,
                'can_supervise_fields': user_profile.can_supervise_fields,
                'can_view_analytics': user_profile.can_view_analytics,
                'can_generate_reports': user_profile.can_generate_reports,
                'can_manage_users': user_profile.can_manage_users,
            })
        except Exception:
            context.update({
                'user_role': None,
                'user_role_display': 'No Role',
                'menu_items': [],
                'can_manage_farms': False,
                'can_track_harvests': False,
                'can_manage_inventory': False,
                'can_supervise_fields': False,
                'can_view_analytics': False,
                'can_generate_reports': False,
                'can_manage_users': False,
            })
    return context