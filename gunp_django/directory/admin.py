from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Department, DownloadLog, KnowledgeBaseArticle, Record, SpeedtestJob, SupportRequest


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip_address', 'last_status', 'last_latency', 'last_checked']
    search_fields = ['name']


class RecordResource(resources.ModelResource):
    class Meta:
        model = Record
        import_id_fields = ['ip_address']
        fields = (
            'id', 'department__name', 'last_name', 'first_name', 'middle_name',
            'ip_address', 'mac_address', 'service', 'office', 'work_phone', 'mobile_phone',
        )


@admin.register(Record)
class RecordAdmin(ImportExportModelAdmin):
    resource_classes = [RecordResource]
    list_display = ['last_name', 'first_name', 'department', 'ip_address', 'mac_address', 'service', 'office']
    list_filter = ['department']
    search_fields = ['last_name', 'first_name', 'ip_address', 'mac_address', 'service']


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'department', 'issue_type', 'status', 'urgency', 'created_at']
    list_filter = ['status', 'urgency']
    search_fields = ['name', 'email', 'description']


@admin.register(KnowledgeBaseArticle)
class KnowledgeBaseArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'updated_at']
    list_filter = ['category']
    search_fields = ['title', 'content']


@admin.register(DownloadLog)
class DownloadLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'filename', 'downloaded_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SpeedtestJob)
class SpeedtestJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'download_mbps', 'upload_mbps', 'ping_ms', 'server_name', 'created_at']
    list_filter = ['status']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
