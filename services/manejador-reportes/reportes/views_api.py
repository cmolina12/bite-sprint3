"""
Vistas REST de la API de reportes.

En esta Etapa 1, las vistas son funcionales pero SIN validación de tenant
(eso se añade en Etapa 3 vía middleware). Los endpoints existen para que el
ALB tenga algo que responder en el Experimento 1 (validar round-robin).

Endpoints:
  GET  /api/tenants/                    — Lista de tenants (debug, no protegido)
  GET  /api/reports/<tenant_slug>/      — Reportes de un tenant
  POST /api/reports/<tenant_slug>/      — Crear reporte (para seed de datos)
  GET  /api/reports/<tenant_slug>/<id>/ — Detalle de un reporte
"""

import json
import logging
import time

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Tenant, Report

logger = logging.getLogger(__name__)


def _report_to_dict(report):
    return {
        "id": report.id,
        "tenant": report.tenant.slug,
        "title": report.title,
        "period": report.period,
        "total_cost_usd": str(report.total_cost_usd),
        "payload": report.payload,
        "created_at": report.created_at.isoformat(),
    }


@csrf_exempt
@require_http_methods(["GET"])
def list_tenants(request):
    """Lista los tenants registrados. Útil para verificar seed."""
    tenants = Tenant.objects.filter(is_active=True).values(
        "id", "name", "slug", "is_active", "created_at"
    )
    return JsonResponse({
        "count": len(tenants),
        "tenants": list(tenants),
        "served_by": settings.INSTANCE_ID,
    }, json_dumps_params={"default": str})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def reports_for_tenant(request, tenant_slug):
    """
    GET  → lista reportes del tenant
    POST → crea un reporte nuevo (sin auth en Etapa 1; en Etapa 3 lo protegemos)
    """
    tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)

    if request.method == "GET":
        # Simulamos un poco de trabajo de "generación de reporte"
        # — esto hace que el Circuit Breaker tenga algo que medir en Exp 1.
        start = time.time()
        reports = Report.objects.filter(tenant=tenant).order_by("-created_at")[:50]
        elapsed_ms = int((time.time() - start) * 1000)

        return JsonResponse({
            "tenant": tenant.slug,
            "count": reports.count(),
            "reports": [_report_to_dict(r) for r in reports],
            "served_by": settings.INSTANCE_ID,
            "query_time_ms": elapsed_ms,
        })

    # POST — crear reporte
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    report = Report.objects.create(
        tenant=tenant,
        title=data.get("title", "Untitled report"),
        period=data.get("period", "2026-Q1"),
        total_cost_usd=data.get("total_cost_usd", 0),
        payload=data.get("payload", {}),
    )
    logger.info("Created report %s for tenant %s", report.id, tenant.slug)
    return JsonResponse(_report_to_dict(report), status=201)


@csrf_exempt
@require_http_methods(["GET"])
def report_detail(request, tenant_slug, report_id):
    """Detalle de un reporte específico."""
    tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
    report = get_object_or_404(Report, id=report_id, tenant=tenant)
    return JsonResponse({
        **_report_to_dict(report),
        "served_by": settings.INSTANCE_ID,
    })
