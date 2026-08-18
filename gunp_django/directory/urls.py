from django.urls import path

from . import views

app_name = 'directory'

urlpatterns = [
    path('', views.index, name='index'),
    path('department/<int:dept_id>/', views.department_detail, name='department'),
    path('department-statuses/', views.department_statuses, name='department_statuses'),
    path('add-record/<int:dept_id>/', views.add_record_public, name='add_record_public'),
    path('search/', views.search, name='search'),
    path('tech-support/', views.tech_support, name='tech_support'),
    path('submit-support-request/', views.submit_support_request, name='submit_support_request'),
    path('check-support-request/', views.check_support_request, name='check_support_request'),
    path('about/', views.about, name='about'),
    path('network-tools/', views.network_tools, name='network_tools'),
    path('ip-calculator/', views.ip_calculator, name='ip_calculator'),
    path('speedtest/', views.run_speedtest, name='speedtest'),
    path('chatbot/', views.chatbot, name='chatbot'),
    path('get-my-ip/', views.get_my_ip, name='get_my_ip'),
    path('resources/', views.resources, name='resources'),
    path('download-form/', views.download_form, name='download_form'),
]
