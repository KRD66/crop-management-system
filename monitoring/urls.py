
from django.urls import path
from . import views

app_name = 'monitoring'

urlpatterns = [ 
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('farm-management/', views.farm_management, name='farm_management'),
    path('harvest-tracking/', views.harvest_tracking, name='harvest_tracking'),
    path('analytics/', views.analytics, name='analytics'),
    path('inventory/', views.inventory, name='inventory'),
    path('reports/', views.reports, name='reports'),
    path('notifications/', views.notifications, name='notifications'),
    path('user-management/', views.user_management, name='user_management'),
    path('api/analytics/yearly-trends/<int:year>/', views.get_yearly_trends, name='yearly_trends'),
    path('api/analytics/farm-efficiency/<int:farm_id>/', views.get_farm_efficiency, name='farm_efficiency'),
    path('reports/', views.reports, name='reports'),
    path('reports/generate/', views.generate_report, name='generate_report')

]

