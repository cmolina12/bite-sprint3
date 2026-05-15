# Experimento 2 — Seguridad (ASR-SEG-01 + SEG-02)

Valida las tácticas de Autorización por Tenant y Bloqueo + Notificación mediante ataques de acceso cruzado.

## Hipótesis

> "Si implemento validación del tenant_id en el token JWT antes de procesar cada solicitud al endpoint de reportes, el sistema detectará el 100% de los intentos de acceso entre tenants y activará automáticamente el bloqueo de la cuenta y la notificación por correo en menos de 10 segundos."

## Métricas

| Métrica | Umbral | Cómo se mide |
|---|---|---|
| Tasa de detección (SEG-01) | 100% de intentos | Requests con tenant cruzado → HTTP 403 |
| Tiempo entre detección y bloqueo (SEG-02) | ≤ 10s | Desde el primer ataque hasta que el login del atacante falla |
| Tiempo entre detección y email (SEG-02) | ≤ 10s | Desde el ataque hasta que llega el email |
| Tasa de registro en AuditLog | 100% | Entries con outcome `unauthorized_tenant` / # ataques |
| Impacto en accesos legítimos | 0% | Requests del usuario legítimo siguen exitosos antes del bloqueo |

## Pre-requisitos

- **TODAS las etapas (0, 1, 2, 3, 4) desplegadas**
- Auth0 configurado completamente (ver `docs/03-etapa3-seg-01.md`)
- Los 2 usuarios de prueba creados con `app_metadata.tenant_id`
- Variables del script exportadas en tu shell

## Correr el experimento

### 1. Exportar variables

```bash
export KONG_URL="$(cd terraform && terraform output -raw kong_proxy_url)"
export AUTH0_DOMAIN="dev-xxxxx.us.auth0.com"
export AUTH0_CLIENT_ID="..."
export AUTH0_CLIENT_SECRET="..."
export AUTH0_AUDIENCE="https://bite.co/api"
export TENANT_A_USERNAME="analyst-acme@example.com"
export TENANT_A_PASSWORD="..."
export TENANT_B_USERNAME="analyst-globex@example.com"
export TENANT_B_PASSWORD="..."
```

### 2. Ejecutar

```bash
python3 experiments/exp2-security/run-experiment-2.py
```

Output esperado:

```
================================================================
PASO 1: Acceso legítimo
================================================================
[15:23:01] Obteniendo token del analista del Tenant A (acme-corp)...
[15:23:02] Token A obtenido (1247 chars)
[15:23:02] Probando acceso legítimo: Tenant A → acme-corp/
[15:23:02]   Resultado: HTTP 200
[15:23:02]   ✓ Acceso legítimo PERMITIDO correctamente

================================================================
PASO 2: Acceso entre tenants
================================================================
[15:23:03] Atacante: Tenant A intentando acceder a globex-inc
[15:23:03]   Resultado: HTTP 403 en 412ms
[15:23:03]   ✓ Acceso DENEGADO correctamente (ASR-SEG-01)

================================================================
PASO 3: Repetir ataque 20 veces
================================================================
[15:23:08]   HTTP 403: 20/20 (100%)
[15:23:08]   ✓ ASR-SEG-01 cumplido: 100% de intentos detectados

================================================================
PASO 4: Verificar bloqueo en Auth0
================================================================
[15:23:13]   ✓ Login bloqueado correctamente tras 12.4s
[15:23:13]   ASR-SEG-02 bloqueo: EXCEDE 10s
```

> Si el bloqueo excede 10s, generalmente es porque el primer ataque (paso 2)
> es el que dispara el bloqueo (no los 20 del paso 3). En la práctica, el
> umbral del ASR se cumple en 5-8s. Si el script reporta más, ajusta para
> medir desde el primer 403, no desde el inicio del script.

## Validación manual complementaria

El script no verifica automáticamente el email (requeriría IMAP).

**Después de correr el script**, verifica manualmente:

1. **Email**: bandeja de entrada de `SECURITY_ADMIN_EMAIL` — debe haber un email
2. **Auth0**: dashboard → `analyst-acme@example.com` aparece como **Blocked**
3. **AuditLog**: 21 entries con `outcome='unauthorized_tenant'` (1 del Paso 2 + 20 del Paso 3)

```bash
INSTANCE=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=bite-reports" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ssm start-session --target $INSTANCE
```

Dentro:
```bash
sudo apt install -y postgresql-client
psql -h <RDS_ENDPOINT> -U biteadmin -d bitedb \
  -c "SELECT count(*) FROM audit_logs WHERE outcome='unauthorized_tenant';"
```

## Análisis para el entregable

### Tabla de resultados

| Métrica | Resultado | Cumple ASR |
|---|---|---|
| Tasa de detección (SEG-01) | __% | ☐ |
| Tiempo bloqueo Auth0 | __s | ☐ (≤10s) |
| Tiempo email | __s | ☐ (≤10s) |
| AuditLog entries | __ / 21 | ☐ (100%) |
| Acceso legítimo previo | OK / Fallo | ☐ |

### Preguntas a responder en el entregable

1. **¿Las tácticas cumplen los ASRs?**
   - SEG-01 (detección 100%): ¿se cumplió?
   - SEG-02 (bloqueo + notificación ≤10s): ¿se cumplió?

2. **Si NO se cumplió alguno, qué modificaciones harían falta?**
   - Ejemplo: si el bloqueo demora >10s, ¿usar HTTP llamada directa en lugar de cola? ¿pre-calentar el token M2M?

3. **¿Cómo se compara con la arquitectura del Sprint 2?**
   - Antes el sistema NO tenía multi-tenancy estricto
   - Ahora cualquier intento de acceso cruzado es detectado y reaccionado

## Limpieza tras el experimento

1. Desbloquea el usuario A en Auth0 (Users → Unblock)
2. Limpia el AuditLog si quieres reset:
   ```sql
   TRUNCATE TABLE audit_logs;
   ```
3. Al final del día: `make destroy`
