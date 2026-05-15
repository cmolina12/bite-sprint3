#!/bin/bash
# =============================================================================
# bootstrap.sh — Provisiona el Manejador de Reportes en una EC2 Ubuntu 24.04.
#
# Lo ejecuta cloud-init como user-data en el primer arranque de cada instancia
# del ASG. Es idempotente: si se ejecuta de nuevo no rompe nada.
#
# Variables esperadas (inyectadas via user-data por Terraform):
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
#   REDIS_HOST, REDIS_PORT
#   GIT_REPO_URL, GIT_REF
#   SECRET_KEY
# =============================================================================

set -euo pipefail
exec > >(tee -a /var/log/bite-bootstrap.log) 2>&1

echo "==> [$(date)] Iniciando bootstrap de BITE.co Manejador de Reportes"

# -----------------------------------------------------------------------------
# 1. Variables de entorno desde el entorno del cloud-init
# -----------------------------------------------------------------------------
# user-data las define previamente con export. Las copiamos a /etc/environment
# para que sobrevivan reboots y estén disponibles para systemd.

EC2_INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id || echo "unknown")

cat >> /etc/environment <<EOF
DJANGO_SETTINGS_MODULE="bite.settings"
DJANGO_SECRET_KEY="${SECRET_KEY}"
DJANGO_DEBUG="False"
DB_HOST="${DB_HOST}"
DB_PORT="${DB_PORT}"
DB_NAME="${DB_NAME}"
DB_USER="${DB_USER}"
DB_PASSWORD="${DB_PASSWORD}"
REDIS_HOST="${REDIS_HOST}"
REDIS_PORT="${REDIS_PORT}"
EC2_INSTANCE_ID="${EC2_INSTANCE_ID}"
AUTH0_DOMAIN="${AUTH0_DOMAIN:-}"
AUTH0_AUDIENCE="${AUTH0_AUDIENCE:-}"
AUTH0_TENANT_CLAIM="${AUTH0_TENANT_CLAIM:-}"
AUTH0_MGMT_CLIENT_ID="${AUTH0_MGMT_CLIENT_ID:-}"
AUTH0_MGMT_CLIENT_SECRET="${AUTH0_MGMT_CLIENT_SECRET:-}"
RABBITMQ_HOST="${RABBITMQ_HOST:-}"
RABBITMQ_PORT="${RABBITMQ_PORT:-5672}"
RABBITMQ_USER="${RABBITMQ_USER:-bite}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-bitepass}"
EOF

# NO usamos `. /etc/environment` porque /etc/environment NO es un script bash
# (es un archivo de pares clave=valor para PAM). Los valores con caracteres
# especiales rompen el `source`. Las variables ya están exportadas en este
# proceso desde el user-data parent, así que NO necesitamos re-leerlas.
echo "==> Variables de entorno ya cargadas desde user-data"

# -----------------------------------------------------------------------------
# 2. Instalar dependencias del sistema
# -----------------------------------------------------------------------------
echo "==> Instalando paquetes del sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    python3 python3-pip python3-venv \
    git \
    libpq-dev \
    build-essential \
    curl \
    postgresql-client

# -----------------------------------------------------------------------------
# 3. Clonar/actualizar el código
# -----------------------------------------------------------------------------
# El repo se clona en /opt/bite/repo/. El código Django vive en el subdirectorio
# services/manejador-reportes/ dentro del repo, así que APP_DIR apunta ahí.
REPO_DIR=/opt/bite/repo
APP_DIR=$REPO_DIR/services/manejador-reportes
mkdir -p /opt/bite

if [ -d "$REPO_DIR/.git" ]; then
    echo "==> Repo ya existe, haciendo pull..."
    cd "$REPO_DIR" && git pull --rebase
else
    echo "==> Clonando $GIT_REPO_URL ($GIT_REF)..."
    git clone --branch "$GIT_REF" --single-branch "$GIT_REPO_URL" "$REPO_DIR"
fi

cd "$APP_DIR"
echo "==> Working dir: $(pwd)"
ls -la

# -----------------------------------------------------------------------------
# 4. Virtualenv + dependencias Python
# -----------------------------------------------------------------------------
echo "==> Configurando virtualenv..."
if [ ! -d /opt/bite/venv ]; then
    python3 -m venv /opt/bite/venv
fi
/opt/bite/venv/bin/pip install --upgrade pip
/opt/bite/venv/bin/pip install -r requirements.txt

# -----------------------------------------------------------------------------
# 5. Migraciones y seed (solo desde la primera instancia que arranque)
# -----------------------------------------------------------------------------
# Las migraciones son idempotentes — Django se da cuenta si ya están aplicadas.
# Ejecutarlas en todas las instancias en paralelo no es peligroso pero sí ruidoso.
# Para Sprint 3 nos da igual; en producción se haría desde un job dedicado.

echo "==> Esperando a que la BD esté lista..."
for i in $(seq 1 30); do
    if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -t 2; then
        echo "    BD disponible"
        break
    fi
    echo "    intento $i/30 — BD no responde aún, esperando 5s..."
    sleep 5
done

echo "==> Aplicando migraciones..."
/opt/bite/venv/bin/python manage.py migrate --noinput

echo "==> Sembrando datos iniciales (idempotente)..."
/opt/bite/venv/bin/python manage.py seed_data || true

# -----------------------------------------------------------------------------
# 6. Configurar Gunicorn como servicio systemd
# -----------------------------------------------------------------------------
echo "==> Configurando systemd service..."
cat > /etc/systemd/system/bite-reportes.service <<'EOF'
[Unit]
Description=BITE.co Manejador de Reportes (Gunicorn)
After=network.target

[Service]
Type=notify
User=root
Group=root
WorkingDirectory=/opt/bite/repo/services/manejador-reportes
EnvironmentFile=/etc/environment
ExecStart=/opt/bite/venv/bin/gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --threads 2 \
    --worker-class gthread \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --timeout 30 \
    --graceful-timeout 10 \
    bite.wsgi:application
Restart=always
RestartSec=5
# El ALB espera 30s entre health checks por defecto. Si el proceso muere,
# queremos que se levante rápido para no marcar la instancia como unhealthy.
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bite-reportes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bite-reportes.service
systemctl restart bite-reportes.service

# -----------------------------------------------------------------------------
# 7. Validación
# -----------------------------------------------------------------------------
echo "==> Esperando a que Gunicorn esté escuchando..."
for i in $(seq 1 20); do
    if curl -sf http://127.0.0.1:8000/health >/dev/null; then
        echo "==> ✓ Servicio respondiendo correctamente"
        curl -s http://127.0.0.1:8000/health
        echo ""
        echo "==> [$(date)] Bootstrap completado"
        exit 0
    fi
    sleep 2
done

echo "==> ✗ Servicio NO responde después de 40s. Revisar logs:"
echo "    journalctl -u bite-reportes -n 50"
exit 1
