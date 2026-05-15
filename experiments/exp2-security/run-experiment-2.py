#!/usr/bin/env python3
"""
Experimento 2 — Seguridad (ASR-SEG-01 + SEG-02)

Hipótesis:
   "Si implemento validación del tenant_id en el token JWT antes de procesar
    cada solicitud al endpoint de reportes, el sistema detectará el 100% de
    los intentos de acceso entre tenants y activará automáticamente el
    bloqueo de la cuenta y la notificación por correo en menos de 10
    segundos."

Pasos:
    1. Acceso legítimo: Tenant A → recursos de Tenant A → debe retornar 200
    2. Acceso cruzado: Tenant A → recursos de Tenant B → debe retornar 403
    3. Repetir el ataque N veces → verificar 100% de detección
    4. Verificar que la cuenta del Tenant A fue bloqueada en Auth0
    5. Verificar que el email llegó al admin (manual o vía IMAP)

Pre-requisitos:
    - Las Etapas 0, 1, 2, 3, 4 deben estar desplegadas
    - Auth0 configurado con dos usuarios:
        * analyst-a@example.com  → app_metadata: {"tenant_id": "acme-corp"}
        * analyst-b@example.com  → app_metadata: {"tenant_id": "globex-inc"}
    - Credenciales de los usuarios y de M2M en variables de entorno

Variables de entorno requeridas:
    KONG_URL              — http://<elastic-ip>:8000
    AUTH0_DOMAIN          — dev-xxxxx.us.auth0.com
    AUTH0_CLIENT_ID       — del Auth0 Application (Regular Web App)
    AUTH0_CLIENT_SECRET   — del Auth0 Application
    AUTH0_AUDIENCE        — https://bite.co/api
    TENANT_A_USERNAME     — email/username del analista de acme-corp
    TENANT_A_PASSWORD     — password del usuario
    TENANT_B_USERNAME     — email/username del analista de globex-inc
    TENANT_B_PASSWORD     — password del usuario
"""

import json
import os
import sys
import time
from datetime import datetime

import requests

# =============================================================================
# Config
# =============================================================================
KONG_URL = os.environ.get("KONG_URL", "").rstrip("/")
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "https://bite.co/api")

TENANT_A_USER = os.environ.get("TENANT_A_USERNAME", "")
TENANT_A_PASS = os.environ.get("TENANT_A_PASSWORD", "")
TENANT_B_USER = os.environ.get("TENANT_B_USERNAME", "")
TENANT_B_PASS = os.environ.get("TENANT_B_PASSWORD", "")

# Validación de configuración
required = {
    "KONG_URL": KONG_URL,
    "AUTH0_DOMAIN": AUTH0_DOMAIN,
    "AUTH0_CLIENT_ID": AUTH0_CLIENT_ID,
    "AUTH0_CLIENT_SECRET": AUTH0_CLIENT_SECRET,
    "TENANT_A_USERNAME": TENANT_A_USER,
    "TENANT_A_PASSWORD": TENANT_A_PASS,
}
missing = [k for k, v in required.items() if not v]
if missing:
    print(f"ERROR: faltan variables de entorno: {', '.join(missing)}")
    sys.exit(1)


# =============================================================================
# Helpers
# =============================================================================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def banner(msg):
    print("\n" + "=" * 64)
    print(msg)
    print("=" * 64)


def get_token(username, password):
    """Obtiene un access_token de Auth0 vía Resource Owner Password Grant."""
    resp = requests.post(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        json={
            "grant_type": "password",
            "username": username,
            "password": password,
            "audience": AUTH0_AUDIENCE,
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "scope": "openid profile email",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        log(f"Error obteniendo token para {username}: {resp.status_code} {resp.text}")
        return None
    return resp.json()["access_token"]


def request_reports(token, tenant_slug):
    """Hace GET a /api/reports/<tenant_slug>/ con el token."""
    return requests.get(
        f"{KONG_URL}/api/reports/{tenant_slug}/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )


# =============================================================================
# Paso 1 — Acceso legítimo
# =============================================================================
banner("PASO 1: Acceso legítimo")
log("Obteniendo token del analista del Tenant A (acme-corp)...")
token_a = get_token(TENANT_A_USER, TENANT_A_PASS)
if not token_a:
    sys.exit(1)
log(f"Token A obtenido ({len(token_a)} chars)")

log("Probando acceso legítimo: Tenant A → acme-corp/")
resp = request_reports(token_a, "acme-corp")
log(f"  Resultado: HTTP {resp.status_code}")
if resp.status_code == 200:
    log("  ✓ Acceso legítimo PERMITIDO correctamente")
else:
    log(f"  ✗ Acceso legítimo bloqueado por error: {resp.text[:200]}")


# =============================================================================
# Paso 2 — Intento de acceso entre tenants
# =============================================================================
banner("PASO 2: Acceso entre tenants (Tenant A → recursos de Tenant B)")
log("Atacante: Tenant A intentando acceder a globex-inc")
attack_start = time.time()
resp = request_reports(token_a, "globex-inc")
attack_elapsed = (time.time() - attack_start) * 1000
log(f"  Resultado: HTTP {resp.status_code} en {attack_elapsed:.0f}ms")
if resp.status_code == 403:
    log("  ✓ Acceso DENEGADO correctamente (ASR-SEG-01)")
else:
    log(f"  ✗ FALLO: el sistema debería retornar 403, retornó {resp.status_code}")
    log(f"     Body: {resp.text[:300]}")


# =============================================================================
# Paso 3 — Repetir N veces para verificar 100% de detección
# =============================================================================
banner("PASO 3: Repetir ataque 20 veces (validar 100% de detección)")
results = []
for i in range(20):
    resp = request_reports(token_a, "globex-inc")
    results.append(resp.status_code)

forbidden = sum(1 for r in results if r == 403)
log(f"  HTTP 403: {forbidden}/20 ({forbidden/20*100:.0f}%)")
log(f"  Esperado para cumplir ASR-SEG-01: 20/20 (100%)")

if forbidden == 20:
    log("  ✓ ASR-SEG-01 cumplido: 100% de intentos detectados")
else:
    log(f"  ✗ ASR-SEG-01 NO cumplido: solo {forbidden}/20 detectados")


# =============================================================================
# Paso 4 — Verificar bloqueo en Auth0 (intentar de nuevo con el token A)
# =============================================================================
banner("PASO 4: Verificar bloqueo en Auth0")
log("Esperando 5 segundos para que se propague el bloqueo...")
time.sleep(5)

log("Intentando obtener un NUEVO token para Tenant A (debería fallar si está bloqueado)")
new_token_a = get_token(TENANT_A_USER, TENANT_A_PASS)
block_elapsed = time.time() - attack_start
if new_token_a is None:
    log(f"  ✓ Login bloqueado correctamente tras {block_elapsed:.1f}s")
    log(f"  ASR-SEG-02 bloqueo: {'OK' if block_elapsed <= 10 else 'EXCEDE 10s'}")
else:
    log("  ✗ El usuario aún puede obtener token — bloqueo no se aplicó")


# =============================================================================
# Paso 5 — Verificación manual de notificación
# =============================================================================
banner("PASO 5: Verificación de notificación por email")
log("Revisa la bandeja de entrada del SECURITY_ADMIN_EMAIL.")
log("Deberías ver un email con asunto:")
log("  '[BITE.co SECURITY] Acceso no autorizado entre tenants detectado'")
log("")
log("Si NO ha llegado en 30s, revisar:")
log(f"  ssh ubuntu@<kong-ip>")
log(f"  sudo docker compose -f /opt/bite/repo/services/kong/docker-compose.yml logs notification-worker")

banner("FIN del experimento")
log(f"Tiempo total: {(time.time() - attack_start):.1f}s")
