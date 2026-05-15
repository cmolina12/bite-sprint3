# =============================================================================
# main.tf — Punto de entrada del proyecto BITE.co Sprint 3
# =============================================================================
# Etapa 0 (esta): infra base — VPC, SGs, RDS, ElastiCache
# Etapa 1: ASR-DISP-01 — Manejador de Reportes ASG + ALB
# Etapa 2: ASR-DISP-02 — Kong con Circuit Breaker
# Etapa 3: ASR-SEG-01 — Middleware tenant + AuditLog
# Etapa 4: ASR-SEG-02 — Auth0 Management API + RabbitMQ + SES/SMTP
# =============================================================================

# Data source para obtener la AMI más reciente de Ubuntu 24.04
# (la usaremos en etapas posteriores)
data "aws_ami" "ubuntu_2404" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Data source para identificar la cuenta (útil para logs)
data "aws_caller_identity" "current" {}
