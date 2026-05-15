# BITE.co Sprint 3 — Etapa 2: Kong + Circuit Breaker (ASR-DISP-02)

Despliega Kong API Gateway entre los clientes y el ALB del Manejador de
Reportes. Kong implementa las dos tácticas de disponibilidad del Sprint 3:

- **Táctica 1 — Health Checks activos**: cada 5s, Kong consulta `/health`
- **Táctica 2 — Circuit Breaker**: si fallan N requests consecutivos, Kong
  abre el circuito y devuelve degradación controlada

## Qué se agrega en esta etapa

| Recurso | Detalle |
|---|---|
| EC2 t2.micro `kong-host` | corre Docker + Docker Compose |
| Elastic IP | IP pública estable para Kong |
| Container Kong 3.7 | proxy en 8000, admin en 8001 |
| Container RabbitMQ 3.13 | preparado para Etapa 4 |
| Container Notification Worker | preparado para Etapa 4 |

## Pre-requisitos

- Etapas 0 y 1 desplegadas y funcionando (`make targets-health` muestra 3 EC2 `healthy`)

## Setup

Si ya hiciste `make apply` con `kong.tf` presente, Kong ya está creado.
Si solo corriste Etapa 0+1 antes, ahora:

```bash
make plan    # debería mostrar +3 recursos: aws_instance.kong, aws_eip.kong, aws_eip_association.kong
make apply
```

Tiempo: ~4 min para crear la EC2 + ~3 min para que el bootstrap de Kong termine = ~7 min.

## Validación

### Test 1 — Kong responde

```bash
KONG=$(make alb-url | sed 's|http://.*|http://|' && echo "no") # cuidado, usa kong_proxy_url:
KONG=$(cd terraform && terraform output -raw kong_proxy_url)
echo $KONG
curl $KONG/health
```

Esperado: el mismo JSON que devuelve `/health` cuando lo consultabas directamente al ALB. La diferencia es que **ahora pasaste por Kong**, y Kong está haciendo health checks contra el ALB.

### Test 2 — Estado del upstream en Kong

```bash
KONG_ADMIN=$(cd terraform && terraform output -raw kong_admin_url)
curl -s $KONG_ADMIN/upstreams/reportes-upstream/health | python3 -m json.tool
```

Esperado:
```json
{
  "data": [
    {
      "target": "bite-reports-alb-...elb.amazonaws.com:80",
      "health": "HEALTHY",
      ...
    }
  ]
}
```

Si dice `HEALTHCHECKS_OFF` o `DNS_ERROR`, ver troubleshooting.

### Test 3 — Round-robin sigue funcionando a través de Kong

```bash
for i in $(seq 1 12); do
  curl -s $KONG/whoami | python3 -c "import sys,json;print(json.load(sys.stdin)['instance_id'])"
done
```

Debes ver los 3 IDs de EC2 rotando (Kong → ALB → 1 de 3 EC2).

### Test 4 — RabbitMQ corre (preparación para Etapa 4)

```bash
RABBIT=$(cd terraform && terraform output -raw rabbitmq_management_url)
echo "Abre en navegador: $RABBIT  (user: bite, pass: bitepass)"
```

> El SG `sg-kong` permite acceso al puerto 15672 solo desde tu IP (`my_ip_cidr`).

## Troubleshooting

### `kong_proxy_url` da connection refused

Las EC2 de Kong tarda ~3 min en terminar el bootstrap. Espera y reintenta.

Conéctate vía Session Manager:

```bash
KONG_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=bite-kong" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ssm start-session --target $KONG_ID
```

Dentro:
```bash
sudo cat /var/log/kong-bootstrap.log    # log del bootstrap
sudo docker ps                           # ver contenedores corriendo
sudo docker logs kong                    # logs de Kong
sudo docker logs rabbitmq
sudo docker logs notification-worker
```

### Upstream "DNS_ERROR" en Kong

El placeholder `__ALB_HOST__` en `kong.yml` no se sustituyó. Verificar:
```bash
sudo cat /opt/bite/repo/services/kong/kong.yml | grep target
```

Debe mostrar la URL real del ALB. Si tiene `__ALB_HOST__`, re-ejecutar bootstrap:
```bash
cd /opt/bite/repo/services/kong
sudo bash ../../bootstrap-kong.sh
```

## Siguiente paso

Una vez los 4 tests pasen → **Etapa 3: Auth0 + Tenant Authorization (ASR-SEG-01)**.

> El **Experimento 1** se puede correr ahora mismo si quieres validar las
> tácticas de disponibilidad sin esperar a Etapas 3 y 4. Ver `docs/05-experimento-1.md`.
