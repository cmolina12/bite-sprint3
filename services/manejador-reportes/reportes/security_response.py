"""
Respuesta automática ante acceso no autorizado — IMPLEMENTACIÓN DE LA TÁCTICA 4
(Bloqueo + Notificación) para el ASR-SEG-02.

Cuando el middleware de tenant detecta un acceso indebido, llama a
`notify_unauthorized_access()` que:

  1. Bloquea la cuenta del usuario en Auth0 via Management API
  2. Publica un evento en RabbitMQ
  3. El worker de notificaciones (en otra EC2) consume el evento y manda email
     al analista legítimo (que es el dueño del tenant atacado) y al admin

Todo esto debe ocurrir en menos de 10 segundos (umbral del ASR-SEG-02).
"""

import json
import logging
from datetime import datetime, timezone

import pika
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Auth0 Management API
# =============================================================================
_mgmt_token_cache = {"token": None, "expires_at": 0}


def _get_mgmt_token():
    """
    Obtiene un token Machine-to-Machine para la Management API de Auth0.

    Lo cacheamos en memoria del proceso (24h de validez típica). En una app
    multi-instancia (como la nuestra con 3 EC2), cada proceso tendrá su
    propio cache, lo cual es aceptable — el rate limit de Auth0 da más que
    suficiente para 3 caches independientes.
    """
    import time
    now = time.time()
    if _mgmt_token_cache["token"] and _mgmt_token_cache["expires_at"] > now + 60:
        return _mgmt_token_cache["token"]

    if not all([settings.AUTH0_MGMT_CLIENT_ID, settings.AUTH0_MGMT_CLIENT_SECRET]):
        raise RuntimeError("Auth0 Management API credentials no configuradas")

    resp = requests.post(
        f"https://{settings.AUTH0_DOMAIN}/oauth/token",
        json={
            "client_id": settings.AUTH0_MGMT_CLIENT_ID,
            "client_secret": settings.AUTH0_MGMT_CLIENT_SECRET,
            "audience": f"https://{settings.AUTH0_DOMAIN}/api/v2/",
            "grant_type": "client_credentials",
        },
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    _mgmt_token_cache["token"] = data["access_token"]
    _mgmt_token_cache["expires_at"] = now + data.get("expires_in", 86400)
    return data["access_token"]


def block_user(user_sub):
    """
    Marca el usuario como blocked=True en Auth0 via Management API.

    El user_sub viene del JWT (claim 'sub'), formato 'auth0|abc123...'
    """
    try:
        token = _get_mgmt_token()
        url = f"https://{settings.AUTH0_DOMAIN}/api/v2/users/{user_sub}"
        resp = requests.patch(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"blocked": True},
            timeout=5,
        )
        resp.raise_for_status()
        logger.info("Auth0 user %s bloqueado exitosamente", user_sub)
        return True
    except Exception as e:
        logger.exception("Error bloqueando usuario %s en Auth0: %s", user_sub, e)
        return False


# =============================================================================
# RabbitMQ — publicación del evento
# =============================================================================
def publish_security_event(event):
    """
    Publica un evento a la cola de notificaciones.
    El worker en la EC2 de Kong lo consume y manda email.
    """
    try:
        credentials = pika.PlainCredentials(
            settings.RABBITMQ_USER, settings.RABBITMQ_PASSWORD
        )
        params = pika.ConnectionParameters(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            credentials=credentials,
            connection_attempts=2,
            retry_delay=1,
            socket_timeout=3,
        )
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(
            queue=settings.RABBITMQ_NOTIFICATIONS_QUEUE, durable=True
        )
        channel.basic_publish(
            exchange="",
            routing_key=settings.RABBITMQ_NOTIFICATIONS_QUEUE,
            body=json.dumps(event).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
            ),
        )
        connection.close()
        logger.info("Evento publicado a RabbitMQ: %s", event.get("type"))
        return True
    except Exception as e:
        logger.exception("Error publicando a RabbitMQ: %s", e)
        return False


# =============================================================================
# Entry point que llama el middleware
# =============================================================================
def notify_unauthorized_access(user_sub, user_tenant, requested_tenant, source_ip):
    """
    Cadena completa de reacción de seguridad ante acceso no autorizado.

    Esta función es la que ejecuta la TÁCTICA 4 (Bloqueo + Notificación)
    para el ASR-SEG-02.
    """
    detected_at = datetime.now(timezone.utc).isoformat()

    # 1. Bloquear al usuario en Auth0
    blocked_ok = block_user(user_sub) if user_sub else False

    # 2. Publicar evento a la cola para que el worker envíe los emails
    event = {
        "type": "unauthorized_tenant_access",
        "detected_at": detected_at,
        "user_sub": user_sub,
        "user_tenant": user_tenant,
        "requested_tenant": requested_tenant,
        "source_ip": source_ip,
        "auth0_blocked": blocked_ok,
    }
    publish_security_event(event)
