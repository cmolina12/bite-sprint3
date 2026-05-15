# BITE.co Sprint 3 — Etapa 1: Manejador de Reportes (base para ASR-DISP-01)

Despliega 3 EC2 con Django detrás de un ALB. Es la **base sobre la que se monta
Kong en la Etapa 2**.

> Recordatorio conceptual: en esta etapa NO se cumple aún la táctica completa
> del Sprint 3 (Kong con Health Checks). El ALB hace sus propios health checks
> y nos sirve de "warm-up". La táctica real se implementa en Etapa 2.

## Qué se agrega en esta etapa

| Recurso | Detalle |
|---|---|
| Launch Template | Ubuntu 24.04, t2.micro, LabInstanceProfile |
| Auto Scaling Group | 3 instancias deseadas (min 1, max 4) |
| Application Load Balancer | HTTP:80, en 2 AZs |
| Target Group | health check sobre `/health` cada 10s |
| Aplicación Django | Gunicorn corriendo como systemd service en cada EC2 |
| Schema en RDS | tablas `tenants`, `reports`, `audit_logs` |
| 2 tenants seed | `acme-corp` y `globex-inc` con 3 reportes cada uno |

## Pre-requisitos

1. **Etapa 0 completada** — `make output` muestra `rds_endpoint` y `redis_endpoint`.
2. **Tu repo en GitHub público** (las EC2 lo clonan al arrancar).
3. **CloudShell abierto en `bite-sprint3/`**.

## Setup paso a paso

### 1. Actualizar `terraform.tfvars`

Añade las variables nuevas de Etapa 1:

```bash
cd terraform
nano terraform.tfvars
```

```hcl
# Etapa 1 — Manejador de Reportes
reports_git_repo_url = "https://github.com/TU_USUARIO/bite-sprint3.git"
reports_git_ref      = "main"

# Genera con: python3 -c "import secrets; print(secrets.token_urlsafe(50))"
django_secret_key = "PEGA_AQUI_LO_QUE_GENERASTE"
```

### 2. Aplicar Terraform

```bash
cd ..
make plan       # debería mostrar ~8 recursos nuevos
make apply
```

Tiempo: **~3 min para crear ALB/ASG + ~5 min para que el bootstrap de cada EC2 termine** = ~8 min total.

### 3. Esperar a que las 3 EC2 estén Healthy

```bash
make targets-health
```

Repite cada 30s hasta que las 3 instancias aparezcan como `healthy`:

```
|  i-0abc...  |  healthy  |
|  i-0def...  |  healthy  |
|  i-0ghi...  |  healthy  |
```

> Si después de 8 minutos siguen en `initial`, ve a Troubleshooting.

### 4. Obtener la URL del ALB

```bash
make alb-url
# http://bite-reports-alb-1234567890.us-east-1.elb.amazonaws.com
```

Guarda esa URL en una variable para los tests:
```bash
ALB=$(make alb-url)
```

## Validación de la Etapa 1

### Test 1 — Health check responde

```bash
curl http://$ALB/health
```

Esperado:
```json
{"status": "ok", "service": "manejador-reportes", "instance_id": "i-xxx", "hostname": "ip-10-20-1-x"}
```

### Test 2 — El ALB balancea entre las 3 EC2

```bash
for i in $(seq 1 12); do
  curl -s http://$ALB/whoami | python3 -c "import sys,json; print(json.load(sys.stdin)['instance_id'])"
done
```

Esperado: 3 instance IDs distintos rotando.

```
i-0abc...
i-0def...
i-0ghi...
i-0abc...
...
```

### Test 3 — API REST funciona

```bash
curl http://$ALB/api/tenants/
curl http://$ALB/api/reports/acme-corp/
curl http://$ALB/api/reports/globex-inc/
curl -o /dev/null -w "%{http_code}\n" http://$ALB/api/reports/nonexistent/  # 404
```

### Test 4 — Conexión a BD funciona

```bash
curl http://$ALB/health/deep
```

Esperado:
```json
{"status": "ok", "checks": {"database": "ok"}, ...}
```

## Troubleshooting

### Las EC2 quedan en estado `unhealthy` o `initial` indefinidamente

**1. Conéctate a una EC2 vía Session Manager** (no necesitas SSH key):

```bash
# Obtén el ID de una instancia
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=bite-reports" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text
```

Copia el `i-xxxx` y abre Session Manager:
```bash
aws ssm start-session --target i-XXXXXXXXXXXX
```

> Si Session Manager falla, otra opción es ir a EC2 en la consola web → seleccionar instancia → "Connect" → "Session Manager".

**2. Logs útiles dentro de la EC2:**

```bash
# Log del bootstrap (qué pasó al arrancar)
sudo cat /var/log/bite-bootstrap.log

# Log del servicio Django
sudo journalctl -u bite-reportes -n 100 --no-pager

# Verificar que el proceso esté corriendo
sudo systemctl status bite-reportes

# Probar el endpoint localmente
curl http://127.0.0.1:8000/health
```

### Errores comunes

| Error en el log | Causa | Solución |
|---|---|---|
| `git clone failed` | URL del repo incorrecta o privado | Verifica que el repo sea público y la URL en `terraform.tfvars` |
| `pg_isready: timeout` | RDS no responde desde la EC2 | Verifica `sg-rds` permite tráfico desde `sg-reports` |
| `ModuleNotFoundError: No module named 'reportes'` | Path incorrecto | Verifica `/opt/bite/manejador-reportes/` existe |
| `address already in use` | Gunicorn ya corría | `sudo systemctl restart bite-reportes` |

### El ALB devuelve 503 Service Unavailable

- Las EC2 aún están haciendo bootstrap. Espera 5-8 min.
- Revisa `make targets-health`. Si todas dicen `unhealthy`, sigue el paso anterior.

### Solo veo 1 instance_id en `/whoami`

- Connection keep-alive del cliente: añade `-H "Connection: close"` al curl.
- Solo 1 instancia healthy: verifica con `make targets-health`.

## Costos acumulados (Etapa 0 + 1)

| Recurso | Costo/hora |
|---|---|
| RDS + ElastiCache (Etapa 0) | $0.034 |
| 3× EC2 t2.micro | $0.035 |
| ALB | $0.022 |
| **Total** | **~$0.091/h** |

8h al día = ~$0.73/día.

## Siguiente paso

Una vez los 4 tests pasen, avanzamos a **Etapa 2: Kong API Gateway con Health
Checks + Circuit Breaker (ASR-DISP-02)** + **Experimento 1**.
