# monitoring/urls.py - URLs that match your existing views only
from django.urls import path
from . import views
from .auth_views import CustomLoginView, CustomLogoutView

app_name = 'monitoring'

urlpatterns = [
    # Authentication URLs
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),

    
    # Main Dashboard
    path('', views.dashboard, name='dashboard'),  # Added for root path
    path('dashboard/', views.dashboard, name='dashboard_alt'),
    
    # User Management (Admin only)
    path('users/', views.user_management, name='user_management'),
    path('users/add/', views.user_add, name='user_add'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/deactivate/', views.user_deactivate, name='user_deactivate'),
    path('users/<int:user_id>/activate/', views.user_activate, name='user_activate'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:user_id>/reset-password/', views.user_reset_password, name='user_reset_password'),
    
    # Profile Management
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('password-reset-request/', views.password_reset_request, name='password_reset_request'),
    
    # Farm Management
    path('farms/', views.farm_management, name='farm_management'),
    
    # Harvest Tracking
    path('harvests/', views.harvest_tracking, name='harvest_tracking'),
    
    # Analytics
    path('analytics/', views.analytics, name='analytics'),
    
    # Inventory Management
    path('inventory/', views.inventory, name='inventory'),
    path('inventory/add/', views.add_inventory, name='add_inventory'),
    path('inventory/remove/', views.remove_inventory, name='remove_inventory'),
    path('inventory/locations/', views.get_inventory_locations, name='get_inventory_locations'),
    path('inventory/summary/', views.inventory_summary, name='inventory_summary'),
    path('inventory/bulk-update/', views.bulk_update_inventory, name='bulk_update_inventory'),
    path('inventory/export/', views.export_inventory, name='export_inventory'),
    
    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/generate/', views.generate_report, name='generate_report'),
    
    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    
    # API Endpoints
    path('api/users/<int:user_id>/toggle-status/', views.api_user_toggle_status, name='api_user_toggle_status'),
    path('api/trends/<int:year>/', views.get_yearly_trends, name='get_yearly_trends'),
    path('api/farm/<int:farm_id>/efficiency/', views.get_farm_efficiency, name='get_farm_efficiency'),
    path('api/metrics/live/', views.get_live_metrics, name='get_live_metrics'),
]