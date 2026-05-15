# Provider AWS configurado para AWS Academy Learner Lab.
# Las credenciales se inyectan via variables de entorno:
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
# que aparecen en "AWS Details -> Show AWS CLI" del Learner Lab.
# IMPORTANTE: estas credenciales caducan cuando se cierra la sesión del lab.

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "BITE.co"
      Sprint      = "3"
      ManagedBy   = "Terraform"
      Environment = "lab"
      Course      = "ISIS-2503"
    }
  }
}
