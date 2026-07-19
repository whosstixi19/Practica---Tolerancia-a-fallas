# Sistema de Reservas — Tolerancia a Fallas

Arquitectura de microservicios con resiliencia aplicada para la materia de Sistemas Distribuidos.

## Integrantes

- Jose Tixi
- Angel Cardenas
- Patricio Lucero

## Arquitectura

```
Cliente HTTP
     │
     ▼
┌─────────────────┐    ┌──────────────────────┐
│  API Gateway     │───▶│  Servicio Reservas   │
│  :8000           │    │  :8001               │
│  + Rate Limiter  │    │  + Circuit Breaker   │
│  (5 req/s por IP)│    │  + Retries (Backoff) │
└─────────────────┘    │  + Fallback Silencioso│
     │                  └──────┬───────┬───────┘
     │                         │       │
     │                  ┌──────▼─┐ ┌───▼──────────┐
     │                  │Invent. │ │ Pagos Stub   │
     │                  │:8002   │ │ :8003        │
     │                  │(Redis) │ │(Latencia 20s)│
     │                  └────────┘ └──────────────┘
     │                         │
     │                  ┌──────▼──────────┐
     │                  │ Notif. Stub     │
     │                  │ :8004           │
     │                  │ (Falla 50%)     │
     │                  └─────────────────┘
```

## Servicios

| Servicio | Puerto | Tech | Dependencias |
|---|---|---|---|
| API Gateway | 8000 | FastAPI + httpx | Reservas |
| Servicio Reservas | 8001 | FastAPI + httpx + tenacity | Inventario, Pagos, Notificaciones |
| Servicio Inventario | 8002 | FastAPI + Redis | Redis |
| Servicio Pagos (Stub) | 8003 | FastAPI | — |
| Servicio Notificaciones (Stub) | 8004 | FastAPI | — |
| Redis | 6379 | — | — |

## Patrones de Resiliencia Implementados

### 1. Rate Limiter (API Gateway)
- **Middleware** que limita a **5 peticiones/segundo por IP**
- Usa `limits` con `MovingWindowRateLimiter` + `MemoryStorage`
- Responde **HTTP 429** cuando se excede el límite

### 2. Circuit Breaker (Servicio Reservas → Pagos)
- **Clase `CircuitBreakerAsincrono`** con `asyncio.Lock` para concurrencia
- **Estados:** CLOSED → OPEN (tras 3 fallos) → HALF-OPEN (tras 30s)
- **Timeout de 3s** en la llamada a Pagos para detectar latencia

### 3. Retry con Backoff Exponencial (Servicio Reservas → Inventario)
- **3 intentos** con `tenacity`
- **Backoff exponencial:** 1s → 2s → 4s
- Filtrado: solo reintenta sobre `httpx.RequestError` y `httpx.HTTPStatusError`

### 4. Fallback Silencioso (Servicio Reservas → Notificaciones)
- `try/except` que captura errores de notificaciones sin interrumpir el flujo
- El usuario siempre recibe confirmación aunque el correo no se envíe

### 5. Rollback Condicional
- Si el pago falla, se ejecuta `/inventario/devolver` solo si el stock fue debitado
- Evita inconsistencias en Redis

## Cómo Ejecutar

### Requisitos
- Docker + Docker Compose
- (Opcional) k6 para pruebas de carga

### Levantar todo
```bash
docker compose up --build
```

### Probar flujo normal
```bash
curl -X POST http://localhost:8000/api/v1/comprar \
  -H "Content-Type: application/json" \
  -d '{"evento_id":"evento_1","cantidad":1,"usuario_email":"test@test.com"}'
```

### Bajar todo
```bash
docker compose down
```

## Escenarios de Prueba / Caos

### Prueba 1 — Rate Limiter
```bash
k6 run tests-chaos/script-carga-k6.js
```
**Esperado:** 200 exitosas + 429 bloqueadas por el Rate Limiter.

### Prueba 2 — Circuit Breaker (Latencia en Pagos)
En `docker-compose.yml`, cambiar `LATENCIA_ACTIVA: "false"` a `"true"` en el servicio `servicio-pagos-stub`, luego:
```bash
docker compose up -d --build
```
**Esperado:** Timeout 3s → Rollback → Circuit Breaker se abre.

### Prueba 3 — Fallback Notificaciones
Dejar `LATENCIA_ACTIVA: "false"`. El stub de notificaciones falla ~50% de las requests por defecto.
```bash
curl -X POST ...  # Ejecutar varias veces
```
**Esperado:** Siempre Status 200, aunque notificaciones falle.

### Prueba 4 — Caos Total (K8s)
```bash
bash tests-chaos/escenarios-caos.sh
```

## Estructura del Proyecto

```
/
├── docker-compose.yml          # Orquestación local
├── src/
│   ├── api_gateway/            # Rate Limiter + proxy
│   ├── servicio_reservas/      # Circuit Breaker + Retries + Fallback
│   ├── servicio_inventario/    # CRUD con Redis
│   ├── servicio_pagos_stub/    # Stub caótico (latencia condicional)
│   └── servicio_notificaciones_stub/  # Stub caótico (falla 50%)
├── k8s-manifests/              # Despliegues para Minikube
├── tests-chaos/                # Scripts de k6 + caos automatizado
└── README.md
```
