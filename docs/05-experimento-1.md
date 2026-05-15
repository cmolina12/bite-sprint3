# Experimento 1 — Disponibilidad (ASR-DISP-01 + DISP-02)

Valida las tácticas de Health Checks y Circuit Breaker tumbando instancias EC2 y midiendo tiempos.

## Hipótesis

> "Si implemento health checks activos y un circuit breaker sobre el Manejador de Reportes, el sistema detectará fallas en ≤ 5 segundos y redirigirá el tráfico a instancias sanas en ≤ 2 segundos, sin que el usuario reciba un error del servidor."

## Métricas a medir

| Métrica | Umbral | Cómo se mide |
|---|---|---|
| Tiempo de detección de falla (DISP-01) | ≤ 5 segundos | Tiempo desde `stop-instances` hasta que Kong marca unhealthy |
| Tiempo de recuperación percibido (DISP-02) | ≤ 2 segundos | Latencia incrementada durante la transición |
| Tasa de error con 1/3 instancias caídas | 0% | Requests exitosas / total |
| Tasa de error con 2/3 instancias caídas | 0% | Requests exitosas / total |
| Respuesta con 3/3 caídas | 503 (no 5xx random) | Códigos HTTP de las respuestas |
| Tiempo de reincorporación | ≤ 10 segundos | Desde `start-instances` hasta healthy |

## Pre-requisitos

- Etapas 0, 1, 2 desplegadas (mínimo necesario)
- 3 EC2 del ASG en estado `healthy` (`make targets-health`)

## Correr el experimento

```bash
bash experiments/exp1-availability/run-experiment-1.sh
```

El script ejecuta automáticamente los 5 pasos del experimento. Output esperado (resumido):

```
PASO 1: Operación normal (3 instancias sanas)
  ✓ Éxito: 30/30, ✗ Falla: 0/30

PASO 2: Falla de 1 instancia
  Víctima: i-0abc...
  Stopping instance i-0abc...
  ✓ Detectado como 'unhealthy' tras 8 segundos      ← MEDICIÓN ASR-DISP-01
  ✓ Éxito: 30/30, ✗ Falla: 0/30                     ← Recovery transparente

PASO 3: Falla de 2 instancias
  Víctima: i-0def...
  ✓ Éxito: 29/30, ✗ Falla: 1/30  (sirve 1 sola)

PASO 4: Falla total
  Víctima: i-0ghi...
  ✓ 200 OK: 0/10
  ⚠️  503 (degradación controlada): 10/10           ← Circuit Breaker activado
  ✗ Otros 5xx: 0/10

PASO 5: Recuperación
  ✓ Éxito: 30/30, ✗ Falla: 0/30

RESUMEN
Tiempo de detección de falla: 8 segundos  (ASR-DISP-01: ≤ 5s)
```

> **Nota importante sobre el tiempo de detección**: el ASG con ALB tiene health
> checks por defecto cada 10s, con `healthy_threshold=2, unhealthy_threshold=2`.
> Por eso el primer detect típico cae entre 10-20s, NO 5s.
>
> Para cumplir el umbral del ASR-DISP-01 estrictamente con Kong, el experimento
> mide el tiempo de detección de **Kong** (`/upstreams/.../health` cada 5s con
> `unhealthy.http_failures: 2` = ~10s) no del ALB.
>
> Si te dan ≥ 5s pero ≤ 10s, en el documento de entregables debes:
> 1. Reportar el valor real
> 2. Explicar que el umbral del Health Check es 5s pero confirmar requiere 2
>    fallas consecutivas (= 10s peor caso)
> 3. Proponer ajuste: reducir `unhealthy.http_failures` a 1 (pero entonces
>    pueden haber falsos positivos por jitter de red)

## Variante con JMeter

Para una medición más rigurosa de la latencia percibida por el usuario:

1. Descarga el plan `Load-tests.jmx` del repo del curso ISIS-2503 (Sprint 2) y modifícalo:
   - **Server Name**: el host de Kong (de `terraform output kong_proxy_url`)
   - **Port**: 8000
   - **Path**: `/health` o `/api/reports/acme-corp/`
2. Configura 10 threads, ramp-up 10s, loop infinito
3. Arranca JMeter ANTES del script de experimento
4. Mientras corre `run-experiment-1.sh`, JMeter va registrando los tiempos
5. Al final, exporta los resultados de **Summary Report**:
   - Average response time
   - Error %
   - Throughput

## Análisis para el entregable

Llena esta tabla con tus resultados:

| Escenario | Threads | Avg Time | Error % | Throughput |
|---|---|---|---|---|
| Normal (3/3) | 10 | __ ms | __% | __ req/s |
| 1/3 caída | 10 | __ ms | __% | __ req/s |
| 2/3 caídas | 10 | __ ms | __% | __ req/s |
| 3/3 caídas | 10 | __ ms | __% | __ req/s |
| Recuperación | 10 | __ ms | __% | __ req/s |

## Análisis de cumplimiento de ASRs

Reflejar en el entregable:

**ASR-DISP-01** (Detección ≤ 5s):
- ¿Se cumplió?
- Si no: ¿qué ajustes harían falta?

**ASR-DISP-02** (Recuperación ≤ 2s sin error 500):
- ¿Se cumplió?
- Si no: ¿qué ajustes harían falta?

## Limpieza

Al final del experimento, las EC2 quedan running. Si quieres validar de nuevo:
```bash
bash experiments/exp1-availability/run-experiment-1.sh
```

Si quieres reiniciar el estado:
```bash
make destroy && make apply
```
