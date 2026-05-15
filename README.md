# BITE.co Sprint 3 — Disponibilidad y Seguridad

Despliegue completo de los ASRs de Disponibilidad (DISP-01, DISP-02) y
Seguridad (SEG-01, SEG-02) sobre AWS, usando las tácticas definidas en el
documento de Sprint 3.

> Este proyecto se corre desde **AWS CloudShell** dentro del Learner Lab de AWS Academy.

## Arquitectura final

```
                ┌─────────────────────┐
                │  Cliente / JMeter   │
                │  / Postman          │
                └──────────┬──────────┘
                           │ HTTP :8000
                           ▼
        ┌───────────────────────────────────────┐
        │  KONG API GATEWAY  (EC2 t2.micro)     │
        │  - Health Checks /health cada 5s      │  Tácticas 1+2
        │  - Circuit Breaker                    │  (DISP-01 + DISP-02)
        │  + RabbitMQ                           │  Etapa 4
        │  + Notification Worker (Docker)       │
        └───────────────────┬───────────────────┘
                            │ HTTP :80
                            ▼
                ┌───────────────────────┐
                │  Application LB       │
                └───────────┬───────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         ┌────────┐    ┌────────┐    ┌────────┐
         │ EC2 #1 │    │ EC2 #2 │    │ EC2 #3 │   Manejador de
         │ Django │    │ Django │    │ Django │   Reportes
         │ +Gunic │    │ +Gunic │    │ +Gunic │   (ASG)
         └───┬────┘    └───┬────┘    └───┬────┘
             │             │             │
             │             ▼             │
             │     ┌──────────────┐      │
             ├────►│ RDS Postgres │◄─────┤
             │     └──────────────┘      │
             │     (tenants, reports,    │
             │      audit_logs)          │
             │                           │
             │     ┌──────────────┐      │
             └────►│ ElastiCache  │◄─────┘
                   │     Redis    │
                   └──────────────┘

                ┌───────────────────────┐
                │   Auth0 (external)    │
                │   - JWT issuance      │  Tácticas 3+4
                │   - Management API    │  (SEG-01 + SEG-02)
                │   - Bloqueo cuentas   │
                └───────────────────────┘
```

## Mapeo Etapa → ASR → Táctica

| Etapa | ASR | Táctica | Componente |
|---|---|---|---|
| 0 | — | — | VPC, RDS, Redis, Security Groups |
| 1 | (base para DISP-01) | — | 3× EC2 con Django + ALB |
| 2 | **DISP-01** + **DISP-02** | Health Checks + Circuit Breaker | Kong en EC2 |
| 3 | **SEG-01** | Autorización basada en Tenant | Middleware Django + Auth0 |
| 4 | **SEG-02** | Bloqueo + Notificación | RabbitMQ + Worker + Auth0 Mgmt API |

## Estructura del proyecto

```
bite-sprint3/
├── terraform/                          # IaC - una sola "receta"
│   ├── versions.tf, providers.tf       # Setup
│   ├── variables.tf                    # Variables configurables
│   ├── network.tf                      # VPC, subnets, IGW
│   ├── security_groups.tf              # 5 SGs en capas
│   ├── persistence.tf                  # RDS Postgres + Redis
│   ├── reports_asg.tf                  # Etapa 1: Launch Template + ASG + ALB
│   ├── kong.tf                         # Etapa 2: EC2 Kong + EIP
│   ├── outputs.tf                      # URLs, IPs, IDs
│   └── terraform.tfvars.example
│
├── services/
│   ├── manejador-reportes/             # App Django principal
│   │   ├── manage.py
│   │   ├── requirements.txt
│   │   ├── bite/                       # config Django
│   │   ├── reportes/                   # app
│   │   │   ├── models.py               # Tenant, Report, AuditLog
│   │   │   ├── views_health.py         # /health, /whoami
│   │   │   ├── views_api.py            # /api/reports/...
│   │   │   ├── auth0_validator.py      # validación JWT (Etapa 3)
│   │   │   ├── middleware/
│   │   │   │   └── tenant_auth.py      # ASR-SEG-01
│   │   │   ├── security_response.py    # ASR-SEG-02
│   │   │   └── management/commands/seed_data.py
│   │   └── scripts/bootstrap.sh        # cold-start de cada EC2 del ASG
│   │
│   ├── kong/                           # API Gateway
│   │   ├── kong.yml                    # config declarativa
│   │   ├── docker-compose.yml          # Kong + RabbitMQ + worker
│   │   └── bootstrap-kong.sh           # cold-start de la EC2 de Kong
│   │
│   └── manejador-notificaciones/       # Worker SMTP
│       ├── Dockerfile
│       └── worker.py
│
├── experiments/
│   ├── exp1-availability/
│   │   └── run-experiment-1.sh         # mata EC2, mide tiempos
│   └── exp2-security/
│       └── run-experiment-2.py         # ataque cross-tenant
│
├── docs/
│   ├── 00-etapa0-infra-base.md
│   ├── 01-etapa1-disp-01.md
│   ├── 02-etapa2-disp-02.md
│   ├── 03-etapa3-seg-01.md             # incluye guía manual de Auth0
│   ├── 04-etapa4-seg-02.md
│   ├── 05-experimento-1.md
│   └── 06-experimento-2.md
│
├── Makefile                            # atajos: init, plan, apply, destroy
└── README.md                           # este archivo
```

## Quickstart

### Setup inicial (una sola vez)

1. **Forkear/clonar este repo** a tu cuenta GitHub (público).
2. **Configurar Auth0** (Etapa 3) — ver `docs/03-etapa3-seg-01.md`.
3. **Configurar Gmail App Password** (Etapa 4) — ver `docs/04-etapa4-seg-02.md`.

### Cada sesión del lab

```bash
# 1. Iniciar el Learner Lab (círculo verde)
# 2. Abrir CloudShell en el portal AWS
# 3. Primera vez:
git clone https://github.com/TU_USUARIO/bite-sprint3.git
cd bite-sprint3

# Siguientes veces:
cd bite-sprint3 && git pull

# 4. Configurar (solo la primera vez)
cd terraform
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars   # llena tus valores

# 5. Aplicar
cd ..
make init      # 1ª vez: ~30s
make plan      # ver qué se crea
make apply     # ~12 min

# 6. Esperar a que las EC2 estén Healthy
make targets-health

# 7. Validar
make output    # ver URLs

# 8. Correr experimentos
bash experiments/exp1-availability/run-experiment-1.sh
python3 experiments/exp2-security/run-experiment-2.py

# 9. AL TERMINAR LA SESIÓN
make destroy   # ~5 min
```

## Documentación detallada

Ve cada archivo en `docs/` en orden:

1. **[00-etapa0-infra-base.md](docs/00-etapa0-infra-base.md)** — VPC, RDS, Redis
2. **[01-etapa1-disp-01.md](docs/01-etapa1-disp-01.md)** — Manejador de Reportes en ASG
3. **[02-etapa2-disp-02.md](docs/02-etapa2-disp-02.md)** — Kong + Circuit Breaker
4. **[03-etapa3-seg-01.md](docs/03-etapa3-seg-01.md)** — Auth0 + validación de tenant
5. **[04-etapa4-seg-02.md](docs/04-etapa4-seg-02.md)** — RabbitMQ + bloqueo + email
6. **[05-experimento-1.md](docs/05-experimento-1.md)** — Disponibilidad
7. **[06-experimento-2.md](docs/06-experimento-2.md)** — Seguridad

## Comandos útiles del Makefile

```bash
make help              # listar todos los comandos
make plan              # ver cambios
make apply             # aplicar cambios
make output            # ver outputs (URLs, etc.)
make targets-health    # ver estado de las EC2 del ASG
make alb-url           # solo la URL del ALB
make destroy           # destruir TODO
```

## Costos en el Learner Lab

| Recurso | Costo/hora |
|---|---|
| RDS db.t3.micro | $0.017 |
| ElastiCache cache.t3.micro | $0.017 |
| 3× EC2 t2.micro (reportes) | $0.035 |
| 1× EC2 t2.micro (kong) | $0.012 |
| ALB | $0.022 |
| Elastic IP (asociada) | $0.000 |
| **Total** | **~$0.10/h** |

Con 8h/día = $0.80/día. El budget de $100 del Learner Lab da para semanas.

> **Importante**: `make destroy` al terminar cada sesión.
