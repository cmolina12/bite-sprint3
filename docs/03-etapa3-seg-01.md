# BITE.co Sprint 3 — Etapa 3: Autorización por Tenant (ASR-SEG-01)

Implementación de la **Táctica 3** del Sprint 3: validación del tenant en el
JWT antes de procesar requests a `/api/reports/<tenant_slug>/...`.

## Flujo

```
Cliente con JWT
    │
    ▼
Kong (no valida el token, solo lo pasa)
    │
    ▼
ALB
    │
    ▼
Django EC2 — TenantAuthorizationMiddleware
    │
    ├─ ¿Authorization header presente?       NO → 401
    ├─ ¿Firma del JWT válida (JWKS)?         NO → 401
    ├─ ¿tenant_id claim presente?            NO → 403
    ├─ ¿tenant_id del JWT == /<slug>/?       NO → 403 + AuditLog + RabbitMQ
    │
    ▼
View
```

Si la validación falla con `outcome=unauthorized_tenant`:
- Se crea entrada en `AuditLog`
- Se publica evento a RabbitMQ
- Se llama a Auth0 Management API para bloquear el usuario (Etapa 4)

## Pre-requisitos

- Etapas 0, 1 y 2 desplegadas y validadas
- Cuenta Auth0 (la del Lab 8 si la conservas)

## Configuración manual de Auth0

> Esta parte NO la hace Terraform — se configura via la web de Auth0.
> Tarda ~15 min la primera vez.

### Paso 1 — Crear API en Auth0

1. Login en https://manage.auth0.com
2. **Applications → APIs → + Create API**
3. Datos:
   - **Name**: `BITE.co Reports API`
   - **Identifier**: `https://bite.co/api`
   - **Signing Algorithm**: `RS256`
4. **Create**

### Paso 2 — Crear Application (Regular Web Application)

Cuando creas la API, Auth0 crea automáticamente una "Test Application" del tipo M2M. Vamos a crear una aplicación adicional para que los usuarios reales hagan login:

1. **Applications → Applications → + Create Application**
2. Nombre: `BITE.co Web App`
3. Tipo: `Regular Web Application`
4. **Create**
5. En **Settings**, anota:
   - **Client ID** → (lo necesitas)
   - **Client Secret** → (lo necesitas)
   - **Domain** → `dev-xxxxx.us.auth0.com`

6. En **Advanced Settings → Grant Types**, activa:
   - ✅ Authorization Code
   - ✅ Refresh Token
   - ✅ **Password** (necesario para que el script de Exp 2 obtenga tokens)
   - ✅ Client Credentials
7. **Save Changes**

### Paso 3 — Habilitar el Password Grant (importante para Exp 2)

Auth0 deshabilita "Resource Owner Password" por defecto. Para activarlo:

1. **Settings → General** (settings del tenant, no de la app)
2. Scroll hasta **API Authorization Settings**
3. **Default Directory** = `Username-Password-Authentication`
4. **Save**

### Paso 4 — Crear los 2 usuarios de prueba

1. **User Management → Users → + Create User**
2. Usuario A:
   - **Email**: `analyst-acme@example.com` (no necesita ser real)
   - **Password**: una segura (12+ chars)
   - **Connection**: `Username-Password-Authentication`
3. Una vez creado, abre el usuario → tab **Details** → scroll hasta **app_metadata**:
   ```json
   {
     "tenant_id": "acme-corp"
   }
   ```
4. **Save**

Repite para usuario B:
- Email: `analyst-globex@example.com`
- Password: otra segura
- `app_metadata`: `{"tenant_id": "globex-inc"}`

> Los valores `acme-corp` y `globex-inc` DEBEN coincidir con los slugs que el seed crea en la BD (`reportes/management/commands/seed_data.py`).

### Paso 5 — Crear el Action que inyecta tenant_id en el JWT

Esto es lo que el Lab 8 hace para inyectar `role`, pero adaptado a `tenant_id`.

1. **Actions → Library → + Create Action**
2. Nombre: `Inject Tenant ID`
3. Trigger: `Login / Post Login`
4. Runtime: `Node 18` (recomendado)
5. **Create**

Código del Action (reemplaza el de ejemplo):

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const namespace = `${event.tenant.id}.us.auth0.com`;  // o usa tu dominio Auth0
  // Alternativa: const namespace = "https://bite.co";
  if (event.user.app_metadata && event.user.app_metadata.tenant_id) {
    api.idToken.setCustomClaim(
      `${namespace}/tenant_id`,
      event.user.app_metadata.tenant_id
    );
    api.accessToken.setCustomClaim(
      `${namespace}/tenant_id`,
      event.user.app_metadata.tenant_id
    );
  }
};
```

> **IMPORTANTE**: anota el `namespace` que uses — ese mismo valor va en
> la variable de entorno `AUTH0_TENANT_CLAIM` para Django (debe quedar como
> `<namespace>/tenant_id` completo).

6. Click **Deploy** (esquina superior derecha)
7. Volver a **Actions → Flows → Login**
8. Arrastra la Action `Inject Tenant ID` desde la columna derecha hasta el flujo
9. **Apply**

### Paso 6 — Crear M2M Application para Management API (necesario para Etapa 4)

Esto permite que Django bloquee usuarios automáticamente.

1. **Applications → Applications → + Create Application**
2. Nombre: `BITE.co Backend M2M`
3. Tipo: `Machine to Machine Application`
4. Click **Create**, te pedirá seleccionar API:
   - Selecciona **Auth0 Management API**
5. Permissions: activa SOLO `update:users`
6. **Authorize**
7. En **Settings**, anota:
   - **Client ID** (lo llamaremos `AUTH0_MGMT_CLIENT_ID`)
   - **Client Secret** (lo llamaremos `AUTH0_MGMT_CLIENT_SECRET`)

## Inyectar las credenciales en las EC2

Las EC2 del ASG necesitan estas variables. Las pasamos vía Terraform.

Edita `terraform/reports_asg.tf` y reemplaza el bloque `cat >> /etc/environment` dentro del user-data para incluir las nuevas variables:

> Nota: en la versión actual del código, el bootstrap.sh ya lee variables
> opcionales. Solo necesitas añadirlas al `local.reports_user_data` en
> `reports_asg.tf` y al `bootstrap.sh` (lo dejé preparado en el código —
> solo descomentas las líneas marcadas como "Etapa 3").

Después:

```bash
make apply
```

Como el `launch_template` cambia, Terraform va a hacer **instance refresh**
del ASG: reemplaza las 3 EC2 una por una sin downtime. Tarda ~10 min.

## Validación

### Test 1 — Sin token

```bash
KONG=$(cd terraform && terraform output -raw kong_proxy_url)
curl -i $KONG/api/reports/acme-corp/
# Esperado: HTTP/1.1 401 — "Missing or malformed Authorization header"
```

### Test 2 — Obtener token de Tenant A

```bash
AUTH0_DOMAIN="dev-xxxxx.us.auth0.com"
CLIENT_ID="..."
CLIENT_SECRET="..."

TOKEN_A=$(curl -s -X POST "https://$AUTH0_DOMAIN/oauth/token" \
  -H "Content-Type: application/json" \
  -d "{
    \"grant_type\": \"password\",
    \"username\": \"analyst-acme@example.com\",
    \"password\": \"TU_PASSWORD\",
    \"audience\": \"https://bite.co/api\",
    \"client_id\": \"$CLIENT_ID\",
    \"client_secret\": \"$CLIENT_SECRET\",
    \"scope\": \"openid profile email\"
  }" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

echo $TOKEN_A | head -c 50; echo "..."
```

### Test 3 — Acceso legítimo

```bash
curl -i -H "Authorization: Bearer $TOKEN_A" $KONG/api/reports/acme-corp/
# Esperado: HTTP/1.1 200 + JSON con reportes
```

### Test 4 — Acceso cruzado (debe fallar)

```bash
curl -i -H "Authorization: Bearer $TOKEN_A" $KONG/api/reports/globex-inc/
# Esperado: HTTP/1.1 403 — "El recurso solicitado no pertenece a tu tenant"
```

### Test 5 — Verificar AuditLog

Conéctate a una EC2 y verifica entries:

```bash
INSTANCE=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=bite-reports" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ssm start-session --target $INSTANCE
```

Dentro:
```bash
sudo -u postgres psql -h <RDS_ENDPOINT> -U biteadmin -d bitedb \
  -c "SELECT timestamp, outcome, user_tenant_slug, requested_tenant_slug FROM audit_logs ORDER BY timestamp DESC LIMIT 10;"
```

## Troubleshooting

### El middleware deja pasar todos los requests

- Verifica que `AUTH0_DOMAIN` esté en `/etc/environment` en la EC2
- Re-arranca Django: `sudo systemctl restart bite-reportes`

### Error "JWT signature invalid"

- El namespace del Action no coincide con `AUTH0_TENANT_CLAIM` en settings
- Decodifica el token en https://jwt.io y mira qué claims tiene

### Error "Token expired"

Tokens duran 24h por defecto. Renueva el token con el comando del Test 2.

## Siguiente paso

**Etapa 4: SEG-02 — Bloqueo + Notificación** (`docs/04-etapa4-seg-02.md`).
