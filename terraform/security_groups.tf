# =============================================================================
# Security Groups
# =============================================================================
# Diseño en capas:
#   - sg_kong:     internet -> Kong (HTTP 8000, HTTPS 8443, admin 8001, SSH)
#   - sg_alb:      Kong -> ALB (HTTP 80)
#   - sg_reports:  ALB -> EC2 reportes (8000) + Kong -> health checks
#   - sg_rds:      EC2 reportes -> RDS (5432)
#   - sg_redis:    EC2 reportes -> Redis (6379)
#   - sg_rabbitmq: EC2 reportes -> RabbitMQ (5672, 15672 admin)
# =============================================================================

# --- Kong API Gateway host ---
resource "aws_security_group" "kong" {
  name        = "${var.project_name}-sg-kong"
  description = "Kong gateway: proxy + admin + SSH + RabbitMQ + Notif worker"
  vpc_id      = aws_vpc.main.id

  # Kong proxy port (donde llegan los requests de los clientes)
  ingress {
    description = "Kong proxy HTTP"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Kong admin API (solo desde tu IP - es sensible)
  ingress {
    description = "Kong admin API (restringido a tu IP)"
    from_port   = 8001
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # RabbitMQ Management UI (solo desde tu IP)
  ingress {
    description = "RabbitMQ Management UI"
    from_port   = 15672
    to_port     = 15672
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  # SSH (solo desde tu IP)
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg-kong"
  }
}

# --- Application Load Balancer ---
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-sg-alb"
  description = "ALB: solo recibe trafico desde Kong"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTP desde Kong"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.kong.id]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg-alb"
  }
}

# --- Manejador de Reportes EC2 instances ---
resource "aws_security_group" "reports" {
  name        = "${var.project_name}-sg-reports"
  description = "Manejador de Reportes: recibe del ALB y de Kong health checks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "App port desde ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Health checks desde Kong"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.kong.id]
  }

  ingress {
    description = "SSH desde tu IP (debugging)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg-reports"
  }
}

# --- RDS PostgreSQL ---
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-sg-rds"
  description = "PostgreSQL: solo desde EC2 reportes"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL desde reportes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.reports.id, aws_security_group.kong.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg-rds"
  }
}

# --- ElastiCache Redis ---
resource "aws_security_group" "redis" {
  name        = "${var.project_name}-sg-redis"
  description = "Redis: solo desde EC2 reportes"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis desde reportes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.reports.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg-redis"
  }
}
