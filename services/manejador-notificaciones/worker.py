"""
Worker que consume eventos de seguridad de RabbitMQ y envía emails via SMTP.

Es el "Manejador de Notificaciones" del Sprint 3. Corre en contenedor Docker
en la EC2 de Kong (no en las EC2 del ASG porque esas no deberían tener
permisos SMTP — separación de responsabilidades).

Cuando llega un evento del tipo 'unauthorized_tenant_access':
  1. Envía email al admin de seguridad (SECURITY_ADMIN_EMAIL)
  2. Envía email "informativo" al analista del tenant atacado (en este lab,
     usamos el admin email como destinatario porque no tenemos lista de
     analistas — en producción se haría lookup en Auth0 o BD)

Se mide:
  - Tiempo entre detección y envío del primer email (debe ser ≤ 10s)
"""

import json
import logging
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pika

# =============================================================================
# Config desde env vars
# =============================================================================
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "bite")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "bitepass")
RABBITMQ_QUEUE = os.environ.get("RABBITMQ_QUEUE", "bite.security.notifications")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
SECURITY_ADMIN_EMAIL = os.environ.get("SECURITY_ADMIN_EMAIL", SMTP_USER)

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("notification-worker")


# =============================================================================
# SMTP
# =============================================================================
def send_email(to_address, subject, body_text):
    """Envía un email via SMTP (Gmail con App Password)."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP no configurado — saltando envío (modo dev)")
        return False

    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Email enviado a %s — '%s'", to_address, subject)
        return True
    except Exception:
        logger.exception("Error enviando email a %s", to_address)
        return False


# =============================================================================
# Handler de eventos
# =============================================================================
def handle_unauthorized_access(event):
    """
    Maneja un evento de tipo unauthorized_tenant_access.
    Envía email al admin de seguridad.
    """
    user_sub = event.get("user_sub", "desconocido")
    user_tenant = event.get("user_tenant", "desconocido")
    requested_tenant = event.get("requested_tenant", "desconocido")
    source_ip = event.get("source_ip", "desconocida")
    detected_at = event.get("detected_at", "")
    blocked = event.get("auth0_blocked", False)

    subject = f"[BITE.co SECURITY] Acceso no autorizado entre tenants detectado"

    body = f"""ALERTA DE SEGURIDAD — BITE.co

Se detectó un intento de acceso no autorizado entre tenants.

Detalles:
---------
  Detectado:           {detected_at}
  Usuario infractor:   {user_sub}
  Tenant del usuario:  {user_tenant}
  Tenant solicitado:   {requested_tenant}
  IP origen:           {source_ip}
  Bloqueo Auth0:       {'EXITOSO ✓' if blocked else 'FALLÓ ✗'}

Acción automática tomada:
-------------------------
  1. La cuenta del usuario fue bloqueada en Auth0 (si fue exitoso)
  2. El intento quedó registrado en AuditLog
  3. Esta notificación fue enviada al equipo de seguridad

Próximos pasos manuales recomendados:
-------------------------------------
  1. Revisar AuditLog para ver si hubo intentos previos del mismo usuario
  2. Contactar al usuario legítimo del tenant {user_tenant} (puede ser
     víctima de robo de credenciales)
  3. Si se confirma robo de credenciales, rotar password y revisar otros
     accesos sospechosos

—
BITE.co Manejador de Notificaciones (Sprint 3)
"""

    # En este lab enviamos solo al admin de seguridad porque no tenemos
    # tabla de "analistas por tenant". En producción se haría:
    #   1. Lookup en Auth0 de usuarios del tenant {user_tenant} con rol analyst
    #   2. Lookup del admin de seguridad del tenant
    #   3. Enviar a ambos
    send_email(SECURITY_ADMIN_EMAIL, subject, body)


# =============================================================================
# Callback de RabbitMQ
# =============================================================================
def on_message(channel, method, properties, body):
    """Callback que se llama por cada mensaje que entra a la cola."""
    receive_time = time.time()
    try:
        event = json.loads(body.decode("utf-8"))
        logger.info("Evento recibido: type=%s", event.get("type"))

        if event.get("type") == "unauthorized_tenant_access":
            handle_unauthorized_access(event)
        else:
            logger.warning("Tipo de evento desconocido: %s", event.get("type"))

        # Ack solo si todo fue bien
        channel.basic_ack(delivery_tag=method.delivery_tag)

        elapsed = (time.time() - receive_time) * 1000
        logger.info("Mensaje procesado en %.0f ms", elapsed)
    except Exception:
        logger.exception("Error procesando mensaje, requeueando")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


# =============================================================================
# Main loop con retry
# =============================================================================
def main():
    logger.info("==> Iniciando Notification Worker")
    logger.info("    RabbitMQ: %s:%s queue=%s", RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_QUEUE)
    logger.info("    SMTP: %s:%s user=%s", SMTP_HOST, SMTP_PORT, SMTP_USER)
    logger.info("    Admin email: %s", SECURITY_ADMIN_EMAIL)

    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )

    # Reintentos de conexión — RabbitMQ puede tardar en arrancar
    for attempt in range(1, 31):
        try:
            connection = pika.BlockingConnection(params)
            break
        except Exception as e:
            logger.warning(
                "Intento %d/30 de conexión a RabbitMQ falló: %s", attempt, e
            )
            time.sleep(3)
    else:
        logger.error("No se pudo conectar a RabbitMQ tras 30 intentos")
        sys.exit(1)

    channel = connection.channel()
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=on_message)

    logger.info("==> Worker listo, esperando mensajes en %s...", RABBITMQ_QUEUE)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Interrumpido por usuario")
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    main()
