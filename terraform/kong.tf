# =============================================================================
# kong.tf — Etapa 2 (ASR-DISP-02)
# =============================================================================
# EC2 dedicada que corre Kong API Gateway en Docker.
# Kong se coloca entre el cliente y el ALB:
#
#   Cliente → Kong (8000) → ALB (80) → 3× EC2 Manejador de Reportes
#
# Kong implementa:
#   - Health Checks activos /health cada 5s (TÁCTICA 1 — ASR-DISP-01)
#   - Circuit Breaker (TÁCTICA 2 — ASR-DISP-02)
#
# La Etapa 4 reusa esta misma EC2 para correr RabbitMQ y el worker de
# notificaciones (todo en Docker Compose).
# =============================================================================

variable "smtp_user" {
  description = "Email Gmail usado para enviar notificaciones (ej: bite.sprint3@gmail.com)"
  type        = string
  default     = ""
}

variable "smtp_password" {
  description = "App Password de Gmail (NO la contraseña real). 16 chars."
  type        = string
  default     = ""
  sensitive   = true
}

variable "smtp_from" {
  description = "Dirección 'From' de los emails (puede ser igual a smtp_user)"
  type        = string
  default     = ""
}

variable "security_admin_email" {
  description = "Email del administrador de seguridad que recibe TODAS las notificaciones"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Elastic IP — para que la IP de Kong sea estable entre reinicios del lab
# -----------------------------------------------------------------------------
resource "aws_eip" "kong" {
  domain = "vpc"
  tags = {
    Name = "${var.project_name}-kong-eip"
  }
}

# -----------------------------------------------------------------------------
# User-data para arrancar Kong
# -----------------------------------------------------------------------------
locals {
  kong_user_data = <<-USERDATA
    #!/bin/bash
    set -euo pipefail

    export ALB_HOST='${aws_lb.reports.dns_name}'
    export GIT_REPO_URL='${var.reports_git_repo_url}'
    export GIT_REF='${var.reports_git_ref}'
    export SMTP_USER='${var.smtp_user}'
    export SMTP_PASSWORD='${var.smtp_password}'
    export SMTP_FROM='${var.smtp_from}'
    export SECURITY_ADMIN_EMAIL='${var.security_admin_email}'

    apt-get update -y
    apt-get install -y git curl

    cd /tmp
    git clone --depth 1 --branch "$GIT_REF" "$GIT_REPO_URL" bite-tmp
    bash bite-tmp/services/kong/bootstrap-kong.sh
  USERDATA
}

# -----------------------------------------------------------------------------
# EC2 instance para Kong
# -----------------------------------------------------------------------------
resource "aws_instance" "kong" {
  ami                         = data.aws_ami.ubuntu_2404.id
  instance_type               = "t2.micro"
  key_name                    = var.key_pair_name
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.kong.id]
  associate_public_ip_address = false  # usamos Elastic IP

  iam_instance_profile = "LabInstanceProfile"

  user_data = local.kong_user_data

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2
  }

  tags = {
    Name = "${var.project_name}-kong"
    Role = "api-gateway"
  }
}

# Asociar la EIP a la instancia
resource "aws_eip_association" "kong" {
  instance_id   = aws_instance.kong.id
  allocation_id = aws_eip.kong.id
}
