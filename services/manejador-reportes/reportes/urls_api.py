"""URLs de la API REST de reportes."""
from django.urls import path
from . import views_api

urlpatterns = [
    path("tenants/", views_api.list_tenants, name="list_tenants"),
    path(
        "reports/<slug:tenant_slug>/",
        views_api.reports_for_tenant,
        name="reports_for_tenant",
    ),
    path(
        "reports/<slug:tenant_slug>/<int:report_id>/",
        views_api.report_detail,
        name="report_detail",
    ),
]
