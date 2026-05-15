"""
Middleware de validación de tenant — IMPLEMENTACIÓN DE LA TÁCTICA 3
(Autorización basada en Tenant) para el ASR-SEG-01.

Flujo:
  1. Request entra con header Authorization: Bearer <jwt>
  2. Middleware valida firma del token contra JWKS de Auth0
  3. Extrae tenant_id del custom claim
  4. Verifica que tenant_id del token COINCIDE con el tenant_slug del path
  5. Si NO coincide → 403 + entrada en AuditLog + publicación a RabbitMQ
  6. Si coincide → request sigue normal

El middleware solo se aplica a rutas /api/reports/<tenant_slug>/...

Rutas públicas (/health, /api/tenants/, admin) no requieren validación.
"""

import logging
import re

from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from ..auth0_validator import (
    validate_token,
    extract_tenant_id,
    TokenValidationError,
    MissingTenantClaim,
)
from ..models import AuditLog

logger = logging.getLogger(__name__)

# Solo validamos tenant en estas rutas
PROTECTED_PATH_PATTERN = re.compile(r"^/api/reports/(?P<tenant_slug>[^/]+)/")


class TenantAuthorizationMiddleware(MiddlewareMixin):
    """
    Middleware que se aplica a rutas /api/reports/<tenant>/... y valida:
      - Token JWT presente y válido
      - tenant_id del JWT == tenant_slug en la URL
    """

    def process_request(self, request):
        # Solo aplicamos a rutas protegidas
        match = PROTECTED_PATH_PATTERN.match(request.path)
        if not match:
            return None  # ruta no protegida, sigue normal

        requested_tenant = match.group("tenant_slug")

        # ¿Está configurado Auth0? Si no, dejamos pasar (Etapa 1 sin auth)
        if not settings.AUTH0_DOMAIN:
            logger.warning(
                "AUTH0_DOMAIN no configurado — middleware en modo permisivo. "
                "Esto solo debería pasar antes de Etapa 3."
            )
            return None

        # -------------------------------------------------------------
        # Extraer token del header
        # -------------------------------------------------------------
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            self._audit(
                request, requested_tenant,
                user_sub=None, user_tenant=None,
                outcome=AuditLog.Outcome.MISSING_TOKEN,
            )
            return JsonResponse(
                {"error": "Missing or malformed Authorization header"},
                status=401,
            )

        token = auth_header.removeprefix("Bearer ").strip()

        # -------------------------------------------------------------
        # Validar firma y expiración
        # -------------------------------------------------------------
        try:
            claims = validate_token(token)
        except TokenValidationError as e:
            logger.info("Token validation failed: %s", e)
            self._audit(
                request, requested_tenant,
                user_sub=None, user_tenant=None,
                outcome=AuditLog.Outcome.INVALID_TOKEN,
            )
            return JsonResponse(
                {"error": f"Invalid token: {e}"},
                status=401,
            )

        # -------------------------------------------------------------
        # Extraer tenant del token
        # -------------------------------------------------------------
        try:
            user_tenant = extract_tenant_id(claims)
        except MissingTenantClaim as e:
            logger.warning("Token sin tenant_id: %s", e)
            self._audit(
                request, requested_tenant,
                user_sub=claims.get("sub"), user_tenant=None,
                outcome=AuditLog.Outcome.INVALID_TOKEN,
            )
            return JsonResponse(
                {"error": "Token missing tenant_id claim"},
                status=403,
            )

        user_sub = claims.get("sub")

        # -------------------------------------------------------------
        # VALIDACIÓN PRINCIPAL: ¿el tenant del token == tenant del recurso?
        # Esta es la línea que implementa el ASR-SEG-01.
        # -------------------------------------------------------------
        if user_tenant != requested_tenant:
            logger.warning(
                "UNAUTHORIZED TENANT ACCESS: user_sub=%s user_tenant=%s requested_tenant=%s",
                user_sub, user_tenant, requested_tenant,
            )
            self._audit(
                request, requested_tenant,
                user_sub=user_sub, user_tenant=user_tenant,
                outcome=AuditLog.Outcome.UNAUTHORIZED_TENANT,
            )

            # Disparar reacción de Etapa 4 (bloqueo + notificación)
            # — el handler maneja errores internamente, no rompe el response
            self._trigger_security_response(
                user_sub=user_sub,
                user_tenant=user_tenant,
                requested_tenant=requested_tenant,
                source_ip=self._client_ip(request),
            )

            return JsonResponse(
                {
                    "error": "Forbidden",
                    "detail": "El recurso solicitado no pertenece a tu tenant.",
                },
                status=403,
            )

        # -------------------------------------------------------------
        # Acceso legítimo — log opcional, sigue al view
        # -------------------------------------------------------------
        self._audit(
            request, requested_tenant,
            user_sub=user_sub, user_tenant=user_tenant,
            outcome=AuditLog.Outcome.ALLOWED,
        )

        # Adjuntamos info útil al request para que la view la use
        request.auth0_claims = claims
        request.user_tenant = user_tenant
        return None

    # =============================================================================
    # Helpers
    # =============================================================================
    def _audit(self, request, requested_tenant, user_sub, user_tenant, outcome):
        """Crea una entrada en AuditLog. Falla silenciosamente si la BD está caída."""
        try:
            AuditLog.objects.create(
                user_sub=user_sub,
                user_tenant_slug=user_tenant,
                requested_tenant_slug=requested_tenant,
                method=request.method,
                path=request.path[:500],
                outcome=outcome,
                source_ip=self._client_ip(request),
                handled_by_instance=settings.INSTANCE_ID,
            )
        except Exception:
            logger.exception("Failed to write AuditLog")

    def _client_ip(self, request):
        """Saca la IP del cliente respetando X-Forwarded-For del ALB/Kong."""
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def _trigger_security_response(self, user_sub, user_tenant, requested_tenant, source_ip):
        """
        Dispara la cadena de reacción de seguridad (Etapa 4).
        Importa dinámicamente para que la Etapa 3 funcione aún sin Etapa 4.
        """
        try:
            from ..security_response import notify_unauthorized_access
            notify_unauthorized_access(
                user_sub=user_sub,
                user_tenant=user_tenant,
                requested_tenant=requested_tenant,
                source_ip=source_ip,
            )
        except Exception:
            logger.exception("Failed to trigger security response")
