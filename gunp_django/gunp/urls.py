from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path('healthz/', views.healthz, name='healthz'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('chat/', include('chat.urls')),
    path('', include('directory.urls')),
]
