"""
URL configuration for BITE.co Manejador de Reportes.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Health check público (sin auth) - para Kong y ALB
    path("", include("reportes.urls_health")),
    # API REST de reportes
    path("api/", include("reportes.urls_api")),
]
