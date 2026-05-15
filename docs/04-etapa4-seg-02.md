# BITE.co Sprint 3 — Etapa 4: Bloqueo + Notificación (ASR-SEG-02)

Implementación de la **Táctica 4** del Sprint 3: reacción automática ante
acceso no autorizado.

## Flujo

```
Middleware detecta acceso cruzado (Etapa 3)
    │
    ▼
security_response.notify_unauthorized_access()
    │
    ├─►  block_user(user_sub)               → Auth0 Mgmt API → user.blocked=true
    │
    └─►  publish_security_event(event)      → RabbitMQ → cola bite.security.notifications
                                                │
                                                ▼
                                       Notification Worker (Docker en EC2 Kong)
                                                │
                                                ▼
                                       Email vía Gmail SMTP → SECURITY_ADMIN_EMAIL
```

Timing objetivo (ASR-SEG-02):
- Detección + bloqueo + email: **≤ 10 segundos**

## Pre-requisitos

- Etapas 0, 1, 2, 3 desplegadas y validadas
- Cuenta Gmail dedicada (recomendado, no uses tu personal) con App Password

## Configuración Gmail App Password

> Si no tienes una cuenta Gmail dedicada, crea una nueva (5 min). NO uses tu
> cuenta personal por seguridad.

1. En la cuenta Gmail, ve a https://myaccount.google.com/security
2. Activa **2-Step Verification** si no está activa
3. Ve a https://myaccount.google.com/apppasswords
4. **Select app**: Mail. **Select device**: Other → "BITE.co Sprint 3"
5. **Generate**
6. Anota los 16 caracteres (sin espacios) — esto es `SMTP_PASSWORD`

## Inyectar credenciales en Terraform

Edita `terraform/terraform.tfvars`:

```hcl
smtp_user            = "bite.sprint3@gmail.com"
smtp_password        = "abcdefghijklmnop"          # los 16 chars
smtp_from            = "bite.sprint3@gmail.com"
security_admin_email = "tu.email.personal@gmail.com"  # dónde llegan las alertas
```

Y aplica:

```bash
make apply
```

Terraform va a recrear la EC2 de Kong para que las nuevas variables se inyecten en `docker-compose.yml`.

## Validación

### Test 1 — Worker conectado a RabbitMQ

```bash
KONG_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=bite-kong" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ssm start-session --target $KONG_ID
```

Dentro:
```bash
sudo docker logs notification-worker --tail 20
# Debes ver: "==> Worker listo, esperando mensajes en bite.security.notifications..."
```

### Test 2 — UI de RabbitMQ

Abre en tu navegador `$(make output | grep rabbitmq_management_url)` (user: `bite`, pass: `bitepass`).

En la pestaña **Queues** debes ver `bite.security.notifications`.

### Test 3 — Trigger end-to-end

Con el token de Tenant A (del Test 2 de Etapa 3):

```bash
curl -i -H "Authorization: Bearer $TOKEN_A" $KONG/api/reports/globex-inc/
# Esperado: HTTP/1.1 403
```

Dentro de 10 segundos:

1. **Email**: revisar la bandeja de `SECURITY_ADMIN_EMAIL` — debe haber un email con asunto `[BITE.co SECURITY] Acceso no autorizado entre tenants detectado`
2. **Auth0**: en el dashboard de Auth0 → **Users** → ver que `analyst-acme@example.com` aparece con marca **"Blocked"**
3. **Intentar volver a loguear**: el token grant ya no funciona

```bash
# Re-correr el comando del Test 2 de Etapa 3 — debería fallar
```

### Test 4 — Auditoría completa en AuditLog

```bash
sudo -u postgres psql -h <RDS> -U biteadmin -d bitedb \
  -c "SELECT timestamp, outcome, user_sub, user_tenant_slug, requested_tenant_slug FROM audit_logs WHERE outcome='unauthorized_tenant' ORDER BY timestamp DESC LIMIT 5;"
```

## Desbloqueo manual (cuando termines de probar)

Para volver a usar el usuario A en tests siguientes:

1. Auth0 → Users → `analyst-acme@example.com` → **Unblock User**
2. O via Management API:
   ```bash
   TOKEN=$(curl -s -X POST "https://$AUTH0_DOMAIN/oauth/token" \
     -H "Content-Type: application/json" \
     -d "{\"client_id\":\"$AUTH0_MGMT_CLIENT_ID\",\"client_secret\":\"$AUTH0_MGMT_CLIENT_SECRET\",\"audience\":\"https://$AUTH0_DOMAIN/api/v2/\",\"grant_type\":\"client_credentials\"}" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

   curl -X PATCH "https://$AUTH0_DOMAIN/api/v2/users/<USER_ID>" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"blocked": false}'
   ```

## Troubleshooting

### El email no llega

```bash
sudo docker logs notification-worker --tail 50
```

Errores comunes:
- `SMTPAuthenticationError`: App Password incorrecta, regenérala
- `SMTPRecipientsRefused`: `SECURITY_ADMIN_EMAIL` mal escrito
- "SMTP no configurado": variables vacías en `.env`

### El usuario no se bloquea en Auth0

```bash
sudo journalctl -u bite-reportes | grep -i auth0
```

Si dice "Auth0 Management API credentials no configuradas", revisa que `AUTH0_MGMT_CLIENT_ID` y `AUTH0_MGMT_CLIENT_SECRET` estén en `/etc/environment` de la EC2.

### Mensaje queda en la cola sin procesar

UI RabbitMQ → Queues → `bite.security.notifications` → "Get messages" para inspeccionar.

Si hay mensajes y el worker no los toma, reiniciar:
```bash
sudo docker restart notification-worker
```

## Siguiente paso

**Experimento 2** (`docs/06-experimento-2.md`) — validar el ASR-SEG-02 con un script automatizado.
