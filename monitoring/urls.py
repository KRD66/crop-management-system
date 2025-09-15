# monitoring/urls.py - URLs that match your existing views only
from django.urls import path
from . import views
from .auth_views import CustomLoginView, CustomLogoutView


app_name = 'monitoring'

urlpatterns = [
    # Authentication URLs
    path('', views.landing_page, name='home'),

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
    path('users/edit-ajax/<int:user_id>/', views.user_edit_ajax, name='user_edit_ajax'),  # New AJAX endpoint
    
    # Profile Management
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('password-reset-request/', views.password_reset_request, name='password_reset_request'),
    
    # Farm Management
    path('farm/management/', views.farm_management, name='farm_management'),
    path('farm/add/', views.farm_add, name='farm_add'),
    path('farm/delete/<int:farm_id>/', views.farm_delete, name='farm_delete'),
    path('farm/detail/<int:farm_id>/', views.farm_detail, name='farm_detail'),
    path('farm/edit/<int:farm_id>/', views.farm_edit, name='farm_edit'),
    # Harvest Tracking
     path('harvests/', views.harvest_tracking, name='harvest_tracking'),
    
    # Analytics
    path('analytics/', views.analytics, name='analytics'),
    
    #inventory
    path('inventory/', views.inventory_dashboard, name='inventory'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('inventory/', views.inventory_dashboard, name='inventory_dashboard'),
    path('inventory/add/', views.add_inventory, name='add_inventory'),
    path('inventory/remove/', views.remove_inventory, name='remove_inventory'),
    path('inventory/adjust/', views.adjust_inventory, name='adjust_inventory'),
    path('inventory/stats/', views.inventory_stats_api, name='inventory_stats_api'),
    path('inventory/locations/', views.get_crop_locations, name='get_crop_locations'),
    path('inventory/history/', views.inventory_history, name='inventory_history'),
    path('inventory/export/', views.export_inventory, name='export_inventory'),
    path('inventory/alerts/', views.low_stock_alert, name='low_stock_alert'),
    

    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/download/<int:report_id>/', views.download_report, name='download_report'),
    
    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    
    # API Endpoints
    path('api/users/<int:user_id>/toggle-status/', views.api_user_toggle_status, name='api_user_toggle_status'),
    path('api/trends/<int:year>/', views.get_yearly_trends, name='get_yearly_trends'),
    path('api/farm/<int:farm_id>/efficiency/', views.get_farm_efficiency, name='get_farm_efficiency'),
    path('api/metrics/live/', views.get_live_metrics, name='get_live_metrics'),
]