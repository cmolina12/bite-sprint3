"""
Vistas de health check — públicas, sin autenticación.

Endpoint principal: /health (consultado por Kong cada 5s para ASR-DISP-01).

Estos endpoints DEBEN responder rápido (<100ms) y NO deben depender de servicios
externos que puedan estar caídos (Auth0, RabbitMQ). Si dependieran de Auth0,
una falla de Auth0 marcaría todo el cluster como no-saludable y Kong tumbaría
el tráfico, lo cual sería un fallo en cascada.

La verificación de BD sí la hacemos pero opcionalmente vía /health/deep, no en /health.
"""

import logging
import socket

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@csrf_exempt
@require_GET
def health(request):
    """
    Liveness probe — responde 200 si el proceso Django está vivo.

    NO verifica BD ni dependencias externas. Si Django responde, está vivo.
    Esta es la respuesta que Kong va a consultar cada 5 segundos.
    """
    return JsonResponse({
        "status": "ok",
        "service": "manejador-reportes",
        "instance_id": settings.INSTANCE_ID,
        "hostname": socket.gethostname(),
    })


@csrf_exempt
@require_GET
def health_deep(request):
    """
    Readiness probe — responde 200 si la app puede atender requests reales.

    Verifica BD. No verifica Redis (porque si Redis cae, la app sigue funcionando
    sin caché, no debe quitarse del balanceo).
    """
    checks = {}
    overall_ok = True

    # DB check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:
        logger.exception("Health check: database failure")
        checks["database"] = f"error: {exc.__class__.__name__}"
        overall_ok = False

    status_code = 200 if overall_ok else 503
    return JsonResponse(
        {
            "status": "ok" if overall_ok else "degraded",
            "service": "manejador-reportes",
            "instance_id": settings.INSTANCE_ID,
            "hostname": socket.gethostname(),
            "checks": checks,
        },
        status=status_code,
    )


@csrf_exempt
@require_GET
def whoami(request):
    """
    Devuelve el instance_id de quien atendió el request.

    Útil para el Experimento 1: con curl en loop podemos validar que el ALB
    está balanceando entre las 3 instancias (los instance_ids van rotando).
    """
    return JsonResponse({
        "instance_id": settings.INSTANCE_ID,
        "hostname": socket.gethostname(),
    })
