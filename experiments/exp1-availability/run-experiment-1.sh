#!/bin/bash
# =============================================================================
# Experimento 1 — Disponibilidad (ASR-DISP-01 + DISP-02)
# =============================================================================
# Hipótesis:
#   "Si implemento health checks activos y un circuit breaker sobre el
#    Manejador de Reportes, el sistema detectará fallas en ≤ 5 segundos y
#    redirigirá el tráfico a instancias sanas en ≤ 2 segundos, sin que el
#    usuario reciba un error del servidor."
#
# Pasos:
#   1. Operación normal: tráfico contra Kong, verificar éxito
#   2. Matar 1 instancia, medir tiempo de detección de Kong (≤ 5s)
#   3. Matar 2ª instancia, medir efecto en usuario (recuperación ≤ 2s)
#   4. Matar 3ª (todas caídas), verificar mensaje de degradación
#   5. Reactivar instancias, medir tiempo de reincorporación
#
# Uso:
#   ./run-experiment-1.sh
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
TERRAFORM_DIR="${TERRAFORM_DIR:-$(cd "$(dirname "$0")/../../terraform" && pwd)}"
LOG_DIR="${LOG_DIR:-/tmp/bite-exp1-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$LOG_DIR"

KONG_URL=$(cd "$TERRAFORM_DIR" && terraform output -raw kong_proxy_url)
KONG_ADMIN_URL=$(cd "$TERRAFORM_DIR" && terraform output -raw kong_admin_url)
ASG_NAME=$(cd "$TERRAFORM_DIR" && terraform output -raw asg_name)

echo "================================================================"
echo "Experimento 1 — Disponibilidad (DISP-01 + DISP-02)"
echo "================================================================"
echo "Kong proxy:    $KONG_URL"
echo "Kong admin:    $KONG_ADMIN_URL"
echo "ASG:           $ASG_NAME"
echo "Logs en:       $LOG_DIR"
echo ""

# -----------------------------------------------------------------------------
# Helper: poll Kong admin para ver health del upstream
# -----------------------------------------------------------------------------
get_upstream_health() {
    curl -s "$KONG_ADMIN_URL/upstreams/reportes-upstream/health" \
        | python3 -c "
import json, sys
data = json.load(sys.stdin)
for node in data.get('data', []):
    print(f\"  - {node.get('target', '?')}: {node.get('health', '?')}\")
" 2>/dev/null || echo "  (Kong admin no responde)"
}

# -----------------------------------------------------------------------------
# Helper: medir un solo request a Kong (devuelve "HTTP_CODE,LATENCY_MS")
# -----------------------------------------------------------------------------
probe_kong() {
    local response
    response=$(curl -s -o /dev/null \
        -w "%{http_code},%{time_total}\n" \
        --max-time 10 \
        "$KONG_URL/health" 2>/dev/null || echo "000,10.0")
    # Convertir time_total (segundos) a milisegundos
    awk -F',' '{printf "%s,%.0f\n", $1, $2*1000}' <<< "$response"
}

# -----------------------------------------------------------------------------
# Helper: listar EC2 IDs del ASG en estado "running"
# -----------------------------------------------------------------------------
list_running_instances() {
    aws autoscaling describe-auto-scaling-groups \
        --auto-scaling-group-names "$ASG_NAME" \
        --query "AutoScalingGroups[0].Instances[?LifecycleState=='InService'].InstanceId" \
        --output text 2>/dev/null
}

# -----------------------------------------------------------------------------
# Helper: matar una instancia EC2 (stop, NO terminate, para reactivarla luego)
# -----------------------------------------------------------------------------
kill_instance() {
    local id="$1"
    echo "  Stopping instance $id..."
    aws ec2 stop-instances --instance-ids "$id" --no-cli-pager > /dev/null
}

restart_instance() {
    local id="$1"
    echo "  Starting instance $id..."
    aws ec2 start-instances --instance-ids "$id" --no-cli-pager > /dev/null
}

# -----------------------------------------------------------------------------
# PASO 1 — Operación normal
# -----------------------------------------------------------------------------
echo "================================================================"
echo "PASO 1: Operación normal (3 instancias sanas)"
echo "================================================================"
echo "Estado del upstream:"
get_upstream_health
echo ""

INSTANCES=($(list_running_instances))
echo "Instancias ejecutándose: ${INSTANCES[@]}"
[ ${#INSTANCES[@]} -lt 3 ] && {
    echo "ERROR: necesitamos 3 instancias para el experimento. Solo hay ${#INSTANCES[@]}."
    exit 1
}

echo ""
echo "Lanzando 30 requests para verificar operación normal..."
SUCCESS=0
FAIL=0
for i in $(seq 1 30); do
    result=$(probe_kong)
    code="${result%,*}"
    if [ "$code" = "200" ]; then
        SUCCESS=$((SUCCESS+1))
    else
        FAIL=$((FAIL+1))
    fi
done
echo "  ✓ Éxito: $SUCCESS/30, ✗ Falla: $FAIL/30"
[ "$FAIL" -gt 0 ] && echo "  ⚠️  Operación normal con errores, revisar antes de continuar"
echo ""

# -----------------------------------------------------------------------------
# PASO 2 — Matar 1ª instancia y medir detección
# -----------------------------------------------------------------------------
echo "================================================================"
echo "PASO 2: Falla de 1 instancia (medir tiempo de detección)"
echo "================================================================"
VICTIM_1="${INSTANCES[0]}"
echo "Víctima: $VICTIM_1"

KILL_TIME=$(date +%s)
kill_instance "$VICTIM_1"

echo ""
echo "Monitoreando hasta que el ALB marque la instancia como unhealthy..."
TG_ARN=$(cd "$TERRAFORM_DIR" && terraform output -raw target_group_arn)
DETECTED_TIME=""
for i in $(seq 1 60); do
    HEALTH=$(aws elbv2 describe-target-health \
        --target-group-arn "$TG_ARN" \
        --query "TargetHealthDescriptions[?Target.Id=='$VICTIM_1'].TargetHealth.State" \
        --output text 2>/dev/null)
    if [ "$HEALTH" = "unhealthy" ] || [ "$HEALTH" = "draining" ] || [ -z "$HEALTH" ]; then
        DETECTED_TIME=$(date +%s)
        ELAPSED=$((DETECTED_TIME - KILL_TIME))
        echo "  ✓ Detectado como '$HEALTH' tras $ELAPSED segundos"
        break
    fi
    sleep 1
done

[ -z "$DETECTED_TIME" ] && echo "  ✗ NO detectado en 60 segundos"

echo ""
echo "Lanzando 30 requests para medir impacto en el usuario..."
SUCCESS=0
FAIL=0
for i in $(seq 1 30); do
    result=$(probe_kong)
    code="${result%,*}"
    if [ "$code" = "200" ]; then
        SUCCESS=$((SUCCESS+1))
    else
        FAIL=$((FAIL+1))
    fi
done
echo "  ✓ Éxito: $SUCCESS/30, ✗ Falla: $FAIL/30"
echo "  Esperado: 0 fallas (Circuit Breaker debe redirigir transparentemente)"

# -----------------------------------------------------------------------------
# PASO 3 — Matar 2ª instancia
# -----------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "PASO 3: Falla de 2 instancias (1 sana de 3)"
echo "================================================================"
VICTIM_2="${INSTANCES[1]}"
echo "Víctima: $VICTIM_2"
kill_instance "$VICTIM_2"
sleep 15

echo ""
echo "Lanzando 30 requests..."
SUCCESS=0
FAIL=0
for i in $(seq 1 30); do
    result=$(probe_kong)
    code="${result%,*}"
    if [ "$code" = "200" ]; then
        SUCCESS=$((SUCCESS+1))
    else
        FAIL=$((FAIL+1))
    fi
done
echo "  ✓ Éxito: $SUCCESS/30, ✗ Falla: $FAIL/30 (sirve 1 sola instancia)"

# -----------------------------------------------------------------------------
# PASO 4 — Falla total
# -----------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "PASO 4: Falla total (0 instancias sanas — debe devolver 5xx graceful)"
echo "================================================================"
VICTIM_3="${INSTANCES[2]}"
echo "Víctima: $VICTIM_3"
kill_instance "$VICTIM_3"
sleep 15

echo ""
echo "Lanzando 10 requests..."
DEGRADATION_COUNT=0
SERVER_ERROR_COUNT=0
SUCCESS_COUNT=0
for i in $(seq 1 10); do
    result=$(probe_kong)
    code="${result%,*}"
    case "$code" in
        200) SUCCESS_COUNT=$((SUCCESS_COUNT+1)) ;;
        503) DEGRADATION_COUNT=$((DEGRADATION_COUNT+1)) ;;
        50?) SERVER_ERROR_COUNT=$((SERVER_ERROR_COUNT+1)) ;;
    esac
done
echo "  ✓ 200 OK: $SUCCESS_COUNT/10"
echo "  ⚠️  503 (degradación controlada): $DEGRADATION_COUNT/10"
echo "  ✗ Otros 5xx: $SERVER_ERROR_COUNT/10"

# -----------------------------------------------------------------------------
# PASO 5 — Recuperación
# -----------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "PASO 5: Recuperación — reactivar instancias"
echo "================================================================"
for inst in "${INSTANCES[@]}"; do
    restart_instance "$inst"
done

echo ""
echo "Esperando 90s para que las instancias arranquen y pasen health check..."
sleep 90

echo ""
echo "Estado final del upstream:"
get_upstream_health

echo ""
echo "Lanzando 30 requests finales..."
SUCCESS=0
FAIL=0
for i in $(seq 1 30); do
    result=$(probe_kong)
    code="${result%,*}"
    if [ "$code" = "200" ]; then
        SUCCESS=$((SUCCESS+1))
    else
        FAIL=$((FAIL+1))
    fi
done
echo "  ✓ Éxito: $SUCCESS/30, ✗ Falla: $FAIL/30"

# -----------------------------------------------------------------------------
# Resumen final
# -----------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "RESUMEN"
echo "================================================================"
echo "Tiempo de detección de falla:  ${ELAPSED:-?} segundos  (ASR-DISP-01: ≤ 5s)"
echo "Logs guardados en:             $LOG_DIR"
echo ""
echo "Para una medición más precisa, complementa con el plan de JMeter:"
echo "  experiments/exp1-availability/load-test.jmx"
