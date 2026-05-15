# =============================================================================
# RDS PostgreSQL 15
# =============================================================================
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-db-subnets"
  }
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.project_name}-postgres"
  engine                 = "postgres"
  engine_version         = "15.7"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  max_allocated_storage  = 0  # Disable autoscaling - Learner Lab tiene límite de 100GB
  storage_type           = "gp2"
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  publicly_accessible    = false
  apply_immediately      = true
  backup_retention_period = 0  # No backups en lab - ahorra costo

  # NOTA: si Learner Lab restringe ciertas versiones de Postgres,
  # ajustar engine_version. 15.x debería estar disponible.

  tags = {
    Name = "${var.project_name}-postgres"
  }
}

# =============================================================================
# ElastiCache Redis 7
# =============================================================================
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project_name}-redis"
  engine               = "redis"
  node_type            = var.redis_node_type
  num_cache_nodes      = 1
  engine_version       = "7.0"
  port                 = 6379
  parameter_group_name = "default.redis7"
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]

  tags = {
    Name = "${var.project_name}-redis"
  }
}
