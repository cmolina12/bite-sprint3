"""
Validación de tokens JWT emitidos por Auth0.

Implementa el patrón del Lab 8 del curso (auth0backend.py) pero adaptado a:
  1. APIs REST con header Authorization: Bearer <token> (no social_django)
  2. Extracción de tenant_id desde el custom claim (no role)
  3. Validación de signature con JWKS de Auth0 (no solo lectura del token)
"""

import json
import logging
from functools import lru_cache

import jwt
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TokenValidationError(Exception):
    """Token inválido (firma, expiración, audience, etc.)"""
    pass


class MissingTenantClaim(TokenValidationError):
    """El token no tiene el custom claim tenant_id"""
    pass


@lru_cache(maxsize=1)
def _get_jwks():
    """
    Descarga el JWKS público de Auth0 una sola vez por proceso.

    El JWKS contiene las llaves públicas con las que Auth0 firma los JWT.
    Lo cacheamos porque cambia rara vez (rotación de claves) y descargarlo
    en cada request agregaría latencia.

    Para Sprint 3 el cache infinito está bien. En producción se haría con
    TTL de unas horas para soportar rotación de claves.
    """
    if not settings.AUTH0_DOMAIN:
        raise TokenValidationError("AUTH0_DOMAIN no configurado")

    jwks_url = f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json"
    response = requests.get(jwks_url, timeout=5)
    response.raise_for_status()
    return response.json()


def _get_signing_key(token):
    """
    Encuentra la llave pública correcta para validar el token.

    Cada JWT tiene en su header un 'kid' (key ID) que identifica qué llave
    del JWKS lo firmó.
    """
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if not kid:
        raise TokenValidationError("Token sin 'kid' en el header")

    jwks = _get_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))

    raise TokenValidationError(f"No se encontró key {kid} en JWKS")


def validate_token(token):
    """
    Valida un token JWT de Auth0 y devuelve los claims.

    Args:
        token: el string del JWT (sin el "Bearer ")

    Returns:
        dict con los claims del token (sub, exp, tenant_id, ...)

    Raises:
        TokenValidationError si el token es inválido por cualquier razón
    """
    if not settings.AUTH0_DOMAIN:
        raise TokenValidationError("AUTH0_DOMAIN no configurado")

    try:
        signing_key = _get_signing_key(token)
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.AUTH0_AUDIENCE,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenValidationError("Token expirado")
    except jwt.InvalidAudienceError:
        raise TokenValidationError(
            f"Audience inválido. Esperado: {settings.AUTH0_AUDIENCE}"
        )
    except jwt.InvalidIssuerError:
        raise TokenValidationError("Issuer inválido")
    except jwt.InvalidTokenError as e:
        raise TokenValidationError(f"Token inválido: {e}")


def extract_tenant_id(claims):
    """
    Extrae el tenant_id desde el custom claim del JWT.

    Equivalente a getRole() del Lab 8, pero para tenant_id.

    En Auth0 los custom claims tienen formato:
        "<namespace>/tenant_id": "<value>"
    donde el namespace es típicamente la URL del tenant Auth0.

    Settings.AUTH0_TENANT_CLAIM contiene ese nombre completo del claim.
    """
    claim_name = settings.AUTH0_TENANT_CLAIM
    tenant_id = claims.get(claim_name)
    if not tenant_id:
        # Intento alternativo: a veces el claim viene sin namespace
        tenant_id = claims.get("tenant_id")

    if not tenant_id:
        raise MissingTenantClaim(
            f"El token no contiene claim '{claim_name}' ni 'tenant_id'. "
            f"Claims disponibles: {list(claims.keys())}"
        )

    return tenant_id
