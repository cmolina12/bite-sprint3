#!/bin/bash
# =============================================================================
# bootstrap-kong.sh — Provisiona la EC2 'kong-host'.
#
# Instala Docker + Docker Compose y arranca el stack:
#   - Kong (API Gateway con Health Checks + Circuit Breaker)
#   - RabbitMQ (cola de notificaciones - Etapa 4)
#   - Notification Worker (consumidor SMTP - Etapa 4)
#
# Variables esperadas (inyectadas via user-data por Terraform):
#   ALB_HOST              — DNS del ALB del Manejador de Reportes
#   GIT_REPO_URL, GIT_REF — repo donde está el código
#   SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SECURITY_ADMIN_EMAIL
# =============================================================================

set -euo pipefail
exec > >(tee -a /var/log/kong-bootstrap.log) 2>&1

echo "==> [$(date)] Iniciando bootstrap de Kong host"

# -----------------------------------------------------------------------------
# 1. Instalar Docker + Docker Compose
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive

echo "==> Instalando paquetes base..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg git

echo "==> Instalando Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# -----------------------------------------------------------------------------
# 2. Clonar repo
# -----------------------------------------------------------------------------
APP_DIR=/opt/bite
mkdir -p "$APP_DIR"

if [ -d "$APP_DIR/repo/.git" ]; then
    echo "==> Repo ya existe, haciendo pull..."
    cd "$APP_DIR/repo" && git pull --rebase
else
    echo "==> Clonando $GIT_REPO_URL ($GIT_REF)..."
    git clone --branch "$GIT_REF" --single-branch "$GIT_REPO_URL" "$APP_DIR/repo"
fi

cd "$APP_DIR/repo/services/kong"

# -----------------------------------------------------------------------------
# 3. Sustituir placeholder __ALB_HOST__ en kong.yml por el DNS real del ALB
# -----------------------------------------------------------------------------
echo "==> Configurando Kong con ALB_HOST=$ALB_HOST..."
sed -i "s|__ALB_HOST__|$ALB_HOST|g" kong.yml

echo "==> Contenido del upstream target en kong.yml:"
grep -A1 "target:" kong.yml

# -----------------------------------------------------------------------------
# 4. Crear archivo .env para docker compose (variables del worker SMTP)
# -----------------------------------------------------------------------------
cat > .env <<EOF
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
SMTP_FROM=${SMTP_FROM}
SECURITY_ADMIN_EMAIL=${SECURITY_ADMIN_EMAIL}
EOF
chmod 600 .env

# -----------------------------------------------------------------------------
# 5. Arrancar el stack
# -----------------------------------------------------------------------------
echo "==> Levantando stack con docker compose..."
docker compose pull
docker compose up -d --build

# -----------------------------------------------------------------------------
# 6. Validación
# -----------------------------------------------------------------------------
echo "==> Esperando a que Kong responda..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8001/status >/dev/null; then
        echo "==> ✓ Kong responde"
        break
    fi
    sleep 2
done

echo "==> Estado del upstream:"
curl -s http://127.0.0.1:8001/upstreams/reportes-upstream/health || true
echo ""

echo "==> Estado de los contenedores:"
docker compose ps

echo "==> [$(date)] Bootstrap de Kong completado"
