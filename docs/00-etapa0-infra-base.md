# BITE.co Sprint 3 — Etapa 0: Infra Base

Infraestructura compartida sobre la cual se montan las 4 etapas de ASRs.

> **Importante**: este proyecto se corre desde **CloudShell** del AWS Learner
> Lab, no desde tu máquina local. CloudShell ya viene autenticado, así que no
> hay que configurar credenciales.

## Qué se crea en esta etapa

| Recurso | Detalle |
|---|---|
| VPC | `10.20.0.0/16`, 2 AZs (`us-east-1a`, `us-east-1b`) |
| Subnets públicas | 2 × `/24` para ALB, Kong, EC2 reportes |
| Subnets privadas | 2 × `/24` para RDS, ElastiCache |
| Internet Gateway | Salida a internet desde subnets públicas |
| Security Groups | `sg-kong`, `sg-alb`, `sg-reports`, `sg-rds`, `sg-redis` |
| RDS PostgreSQL 15 | `db.t3.micro`, 20 GB gp2, no public, no backups |
| ElastiCache Redis 7 | `cache.t3.micro`, 1 nodo |

## Pre-requisitos

1. Una sesión activa del **AWS Academy Learner Lab** (botón verde "Start Lab").
2. El código de este proyecto subido a un **repositorio público de GitHub**.

## Setup paso a paso

### 1. Subir el código a GitHub (una sola vez)

Desde tu laptop:

```bash
unzip bite-sprint3-etapa1.zip
cd bite-sprint3

git init
git add .
git commit -m "BITE.co Sprint 3 - Etapas 0 y 1"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/bite-sprint3.git
git push -u origin main
```

### 2. Abrir CloudShell del Learner Lab

En el portal del lab, click en el **ícono de terminal** (esquina superior derecha de la consola AWS) o busca **CloudShell** en el buscador.

> CloudShell ya tiene `terraform`, `aws cli`, `git`, `python3` preinstalados. No tienes que instalar nada.

### 3. Clonar tu repo

```bash
git clone https://github.com/TU_USUARIO/bite-sprint3.git
cd bite-sprint3
```

### 4. Configurar `terraform.tfvars`

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

Edita estos valores:

```hcl
# Tu IP pública. CloudShell te la da con:
#   curl -s ifconfig.me
my_ip_cidr = "TU_IP/32"

# Password de PostgreSQL. Genera con:
#   openssl rand -hex 12
db_password = "TU_PASSWORD"
```

> Las variables de Etapa 1 (`reports_git_repo_url`, `django_secret_key`, etc.)
> también van aquí, pero pueden quedar en sus defaults si solo vas a probar
> Etapa 0.

Guarda con `Ctrl+X`, `Y`, `Enter`.

### 5. Aplicar Terraform

Vuelve a la raíz del proyecto:

```bash
cd ..
make init       # primera vez: descarga el provider de AWS (~30s)
make plan       # ver qué se va a crear
make apply      # confirmar con 'yes'
```

Tiempo estimado: **~8–12 minutos** (RDS es lo más lento).

### 6. Verificar outputs

```bash
make output
```

Deberías ver:
```
rds_endpoint     = "bite-postgres.xxxxx.us-east-1.rds.amazonaws.com"
redis_endpoint   = "bite-redis.xxxxx.cache.amazonaws.com"
vpc_id           = "vpc-0xxxxxxxx"
...
```

Guarda estos valores; se usarán en etapas siguientes.

## Destruir todo al final de la sesión

**MUY IMPORTANTE**: el lab cobra mientras los recursos existan, aunque la sesión esté detenida. Al terminar tu trabajo del día:

```bash
make destroy   # confirmar con 'yes'
```

Tiempo: ~5 min.

> Cuando retomes mañana: re-inicia el lab, abre CloudShell, `cd bite-sprint3`,
> `make apply`. El repo persiste en CloudShell entre sesiones.

## Troubleshooting

### `Error creating RDS DB Instance: InvalidParameterValue: Cannot find version 15.7`

La versión exacta de Postgres puede variar. Edita `terraform/persistence.tf`:
```hcl
engine_version = "15"
```

### `Error: vockey key pair not found`

El key pair `vockey` solo existe en `us-east-1`. Verifica que `aws_region = "us-east-1"` en `variables.tf`.

### El `terraform apply` queda atascado en RDS

Es normal: RDS tarda 5-7 min. Si pasa de 15 min, abre otra pestaña de CloudShell y revisa estado:
```bash
aws rds describe-db-instances --db-instance-identifier bite-postgres --query 'DBInstances[0].DBInstanceStatus'
```

## Costos estimados

| Recurso | Costo/hora |
|---|---|
| RDS db.t3.micro | $0.017 |
| ElastiCache cache.t3.micro | $0.017 |
| **Etapa 0** | **~$0.034/h** |

Si destruyes al terminar cada día, gastas <$1/día. El budget de $100 del Learner Lab cubre meses de iteración.

## Siguiente paso

Una vez `make output` muestra los recursos correctamente → **Etapa 1: Manejador de Reportes + ALB + Health Checks**.
