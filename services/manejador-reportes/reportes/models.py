"""
Modelos del Manejador de Reportes — BITE.co Sprint 3.

Tenant      → empresa cliente de BITE.co (multi-tenancy)
Report      → reporte de costos cloud generado para un tenant específico
AuditLog    → registro de intentos de acceso (legítimos y no autorizados) — usado en SEG-01
"""

from django.db import models


class Tenant(models.Model):
    """
    Empresa cliente de BITE.co. Cada Tenant representa una organización
    que tiene sus propios datos de costos cloud aislados de otros tenants.
    """

    name = models.CharField(max_length=100, unique=True)
    # Identificador externo que se usa en el JWT claim (puede ser el mismo `id`
    # o un UUID/slug para mayor opacidad - aquí usamos un slug por legibilidad)
    slug = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class Report(models.Model):
    """
    Reporte de costos cloud generado para un tenant.

    Nota: en producción real, BITE.co tendría modelos más ricos (CloudProvider,
    CostRecord, BillingPeriod, etc.). Para Sprint 3 nos quedamos con Report
    simple porque lo importante a validar son las TÁCTICAS de disponibilidad
    y seguridad, no la lógica de negocio.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="reports"
    )
    title = models.CharField(max_length=200)
    period = models.CharField(
        max_length=20,
        help_text="Período del reporte, ej: '2026-Q1', '2026-05'",
    )
    total_cost_usd = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    payload = models.JSONField(
        default=dict,
        help_text="Detalle del reporte (breakdown por servicio, región, etc.)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.tenant.slug}/{self.period} — ${self.total_cost_usd}"


class AuditLog(models.Model):
    """
    Registro de cada intento de acceso a recursos protegidos.

    Usado en ASR-SEG-01: detección de acceso entre tenants. Cuando un usuario
    autenticado del Tenant A intenta acceder a recursos del Tenant B, se
    crea una entrada con outcome='unauthorized_tenant'.

    Implementado en la Etapa 1 (modelo) pero solo se POPULA desde la Etapa 3.
    """

    class Outcome(models.TextChoices):
        ALLOWED = "allowed", "Allowed"
        UNAUTHORIZED_TENANT = "unauthorized_tenant", "Unauthorized Tenant Access"
        INVALID_TOKEN = "invalid_token", "Invalid Token"
        MISSING_TOKEN = "missing_token", "Missing Token"

    timestamp = models.DateTimeField(auto_now_add=True)
    # Usuario que hizo el request (subject del JWT). Puede ser null si no había token.
    user_sub = models.CharField(max_length=255, null=True, blank=True)
    # Tenant del usuario (el que firma el JWT)
    user_tenant_slug = models.CharField(max_length=50, null=True, blank=True)
    # Tenant del recurso al que intentó acceder
    requested_tenant_slug = models.CharField(max_length=50, null=True, blank=True)
    # Endpoint
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    # Resultado
    outcome = models.CharField(max_length=30, choices=Outcome.choices)
    # IP del request (X-Forwarded-For del ALB)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    # Instance ID del Manejador de Reportes que atendió el request
    handled_by_instance = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["user_sub", "-timestamp"]),
            models.Index(fields=["outcome", "-timestamp"]),
        ]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {self.outcome} {self.method} {self.path}"
