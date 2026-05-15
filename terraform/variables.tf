# =============================================================================
# Variables generales
# =============================================================================
variable "aws_region" {
  description = "Región AWS. Learner Lab solo permite us-east-1 o us-west-2. Usar us-east-1 para tener vockey disponible."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefijo para nombrar recursos. Mantener corto (<=10 chars) por límites de AWS."
  type        = string
  default     = "bite"
}

variable "key_pair_name" {
  description = "Nombre del key pair de EC2. En Learner Lab us-east-1 viene 'vockey' pre-creado."
  type        = string
  default     = "vockey"
}

# =============================================================================
# Networking
# =============================================================================
variable "vpc_cidr" {
  description = "CIDR de la VPC del proyecto"
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDRs de subnets públicas (Kong, ALB, NAT). Mínimo 2 AZs para ALB."
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDRs de subnets privadas (EC2 reportes, RDS, ElastiCache)."
  type        = list(string)
  default     = ["10.20.11.0/24", "10.20.12.0/24"]
}

variable "availability_zones" {
  description = "AZs a usar. En us-east-1 elegimos 1a y 1b por disponibilidad típica en Learner Lab."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "my_ip_cidr" {
  description = "Tu IP pública en formato CIDR para acceso SSH a Kong y a los EC2. Ej: '181.49.xx.xx/32'. Si no la sabes, ejecuta 'curl ifconfig.me'."
  type        = string
  # SIN default a propósito - obliga a que el usuario lo defina en terraform.tfvars
}

# =============================================================================
# Persistencia (reutilizadas del Sprint 2 conceptualmente, recreadas en este lab)
# =============================================================================
variable "db_username" {
  description = "Usuario master de PostgreSQL"
  type        = string
  default     = "biteadmin"
}

variable "db_password" {
  description = "Password master de PostgreSQL. Mínimo 8 caracteres. Defínelo en terraform.tfvars (NO commitear)."
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Nombre de la base de datos inicial"
  type        = string
  default     = "bitedb"
}

variable "db_instance_class" {
  description = "Clase de instancia RDS. db.t3.micro está dentro del Learner Lab."
  type        = string
  default     = "db.t3.micro"
}

variable "redis_node_type" {
  description = "Tipo de nodo de ElastiCache."
  type        = string
  default     = "cache.t3.micro"
}
