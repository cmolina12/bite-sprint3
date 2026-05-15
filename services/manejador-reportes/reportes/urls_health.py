"""URLs públicas de health check (sin auth)."""
from django.urls import path
from . import views_health

urlpatterns = [
    path("health", views_health.health, name="health"),
    path("health/deep", views_health.health_deep, name="health_deep"),
    path("whoami", views_health.whoami, name="whoami"),
]
