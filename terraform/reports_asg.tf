# =============================================================================
# reports_asg.tf — Etapa 1 (ASR-DISP-01)
# =============================================================================
# Despliega el Manejador de Reportes en 3 EC2 detrás de un ALB:
#
#   Cliente → ALB (80) → 3× EC2 t2.micro (8000) corriendo Gunicorn → Django app
#
# El ALB hace sus propios health checks contra /health. Esto NO es la táctica
# Health Checks del Sprint 3 (esa la implementa Kong en la Etapa 2), pero sí
# nos permite validar en esta etapa que las 3 instancias responden y el
# balanceo funciona antes de añadir Kong encima.
# =============================================================================

# -----------------------------------------------------------------------------
# Variables específicas de la Etapa 1
# -----------------------------------------------------------------------------
variable "reports_git_repo_url" {
  description = "URL del repo público (o accesible) con el código del Manejador de Reportes."
  type        = string
  # En tu lab: pondrás la URL de tu fork/repo personal en terraform.tfvars
}

variable "reports_git_ref" {
  description = "Branch o tag del repo a clonar."
  type        = string
  default     = "main"
}

variable "reports_instance_type" {
  description = "Tipo de EC2 para el Manejador de Reportes. t2.micro está en free tier."
  type        = string
  default     = "t2.micro"
}

variable "reports_asg_desired" {
  description = "Cantidad de instancias deseadas en el ASG. Mínimo 3 para Experimento 1."
  type        = number
  default     = 3
}

variable "reports_asg_min" {
  description = "Mínimo de instancias en el ASG."
  type        = number
  default     = 1
}

variable "reports_asg_max" {
  description = "Máximo de instancias en el ASG."
  type        = number
  default     = 4
}

variable "django_secret_key" {
  description = "SECRET_KEY de Django. Genera uno con: python -c 'import secrets; print(secrets.token_urlsafe(50))'"
  type        = string
  sensitive   = true
}

# -----------------------------------------------------------------------------
# Variables de Auth0 (Etapa 3 — SEG-01 y SEG-02)
# Pueden quedar vacías hasta que configures Auth0. Si están vacías, el
# middleware de tenant entra en "modo permisivo" (deja pasar todo).
# -----------------------------------------------------------------------------
variable "auth0_domain" {
  description = "Domain de tu tenant Auth0. Ej: dev-xxxxx.us.auth0.com"
  type        = string
  default     = ""
}

variable "auth0_audience" {
  description = "Audience (Identifier) de la API en Auth0. Ej: https://bite.co/api"
  type        = string
  default     = "https://bite.co/api"
}

variable "auth0_tenant_claim" {
  description = "Claim completo del JWT donde Django busca el tenant_id. Ej: https://bite.co/tenant_id"
  type        = string
  default     = "https://bite.co/tenant_id"
}

variable "auth0_mgmt_client_id" {
  description = "Client ID de la M2M Application para Management API (bloqueo de usuarios)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "auth0_mgmt_client_secret" {
  description = "Client Secret de la M2M Application para Management API."
  type        = string
  default     = ""
  sensitive   = true
}

# -----------------------------------------------------------------------------
# User-data script (cloud-init) que se ejecutará en cada EC2 al arrancar
# -----------------------------------------------------------------------------
locals {
  reports_user_data = <<-USERDATA
    #!/bin/bash
    set -euo pipefail

    # Inyecta variables de entorno que bootstrap.sh espera
    export DB_HOST='${aws_db_instance.postgres.address}'
    export DB_PORT='${aws_db_instance.postgres.port}'
    export DB_NAME='${aws_db_instance.postgres.db_name}'
    export DB_USER='${var.db_username}'
    export DB_PASSWORD='${var.db_password}'
    export REDIS_HOST='${aws_elasticache_cluster.redis.cache_nodes[0].address}'
    export REDIS_PORT='6379'
    export SECRET_KEY='${var.django_secret_key}'
    export GIT_REPO_URL='${var.reports_git_repo_url}'
    export GIT_REF='${var.reports_git_ref}'

    # --- Auth0 (Etapa 3 - SEG-01) ---
    # Si están vacíos, el middleware queda en modo permisivo.
    export AUTH0_DOMAIN='${var.auth0_domain}'
    export AUTH0_AUDIENCE='${var.auth0_audience}'
    export AUTH0_TENANT_CLAIM='${var.auth0_tenant_claim}'
    export AUTH0_MGMT_CLIENT_ID='${var.auth0_mgmt_client_id}'
    export AUTH0_MGMT_CLIENT_SECRET='${var.auth0_mgmt_client_secret}'

    # --- RabbitMQ (Etapa 4 - SEG-02) ---
    # Apunta a la Elastic IP de Kong, donde corre el broker.
    export RABBITMQ_HOST='${aws_instance.kong.private_ip}'
    export RABBITMQ_PORT='5672'
    export RABBITMQ_USER='bite'
    export RABBITMQ_PASSWORD='bitepass'

    # Descarga el bootstrap del repo (clonamos rápido solo el script)
    apt-get update -y
    apt-get install -y git curl
    cd /tmp
    git clone --depth 1 --branch "$GIT_REF" "$GIT_REPO_URL" bite-tmp
    bash bite-tmp/services/manejador-reportes/scripts/bootstrap.sh
  USERDATA
}

# -----------------------------------------------------------------------------
# Launch Template
# -----------------------------------------------------------------------------
resource "aws_launch_template" "reports" {
  name_prefix   = "${var.project_name}-reports-"
  image_id      = data.aws_ami.ubuntu_2404.id
  instance_type = var.reports_instance_type
  key_name      = var.key_pair_name

  vpc_security_group_ids = [aws_security_group.reports.id]

  # LabInstanceProfile pre-creado en Learner Lab
  iam_instance_profile {
    name = "LabInstanceProfile"
  }

  user_data = base64encode(local.reports_user_data)

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      delete_on_termination = true
    }
  }

  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-reports"
      Role = "manejador-reportes"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# -----------------------------------------------------------------------------
# Application Load Balancer
# -----------------------------------------------------------------------------
resource "aws_lb" "reports" {
  name               = "${var.project_name}-reports-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false
  idle_timeout               = 60

  tags = {
    Name = "${var.project_name}-reports-alb"
  }
}

# -----------------------------------------------------------------------------
# Target Group
# -----------------------------------------------------------------------------
resource "aws_lb_target_group" "reports" {
  name     = "${var.project_name}-reports-tg"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id

  # Health checks del ALB — NO son la táctica de DISP-01, esa la hace Kong.
  # Estos sirven para que el ALB no enrute tráfico a instancias muertas.
  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 10
    timeout             = 5
    matcher             = "200"
  }

  deregistration_delay = 30  # tiempo de drenaje al sacar una instancia

  tags = {
    Name = "${var.project_name}-reports-tg"
  }
}

# -----------------------------------------------------------------------------
# ALB Listener
# -----------------------------------------------------------------------------
resource "aws_lb_listener" "reports" {
  load_balancer_arn = aws_lb.reports.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.reports.arn
  }
}

# -----------------------------------------------------------------------------
# Auto Scaling Group
# -----------------------------------------------------------------------------
resource "aws_autoscaling_group" "reports" {
  name             = "${var.project_name}-reports-asg"
  desired_capacity = var.reports_asg_desired
  min_size         = var.reports_asg_min
  max_size         = var.reports_asg_max

  vpc_zone_identifier = aws_subnet.public[*].id
  target_group_arns   = [aws_lb_target_group.reports.arn]

  launch_template {
    id      = aws_launch_template.reports.id
    version = "$Latest"
  }

  # Health checks: usamos ELB para que el ASG mate instancias que el ALB
  # marca como unhealthy (no solo por fallas de EC2 sino también de la app).
  health_check_type         = "ELB"
  health_check_grace_period = 180  # 3 min para que bootstrap.sh termine

  # Estrategia de instance refresh: si actualizamos el launch template,
  # AWS reemplaza las instancias gradualmente sin downtime.
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 50
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.project_name}-reports"
    propagate_at_launch = true
  }

  tag {
    key                 = "Project"
    value               = "BITE.co"
    propagate_at_launch = true
  }

  # Importante: no esperamos a que TODAS las instancias estén healthy
  # antes de devolver el control, porque el bootstrap tarda ~3-4 min.
  wait_for_capacity_timeout = "0"

  lifecycle {
    create_before_destroy = true
  }
}
