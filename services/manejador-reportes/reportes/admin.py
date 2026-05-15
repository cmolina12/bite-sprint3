from django.contrib import admin
from .models import Tenant, Report, AuditLog


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "period", "total_cost_usd", "created_at")
    list_filter = ("tenant", "period")
    search_fields = ("title", "tenant__slug")
    date_hierarchy = "created_at"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp", "outcome", "method", "path",
        "user_sub", "user_tenant_slug", "requested_tenant_slug",
    )
    list_filter = ("outcome", "method")
    search_fields = ("user_sub", "path", "user_tenant_slug")
    date_hierarchy = "timestamp"
    readonly_fields = [f.name for f in AuditLog._meta.fields]
