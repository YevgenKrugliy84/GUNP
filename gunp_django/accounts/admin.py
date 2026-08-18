from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('GUNP', {'fields': ('department',)}),
    )
    list_display = ['username', 'department', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_active', 'department']
    search_fields = ['username', 'department']
