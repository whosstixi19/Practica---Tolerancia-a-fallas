# Sistema de Reservas — Tolerancia a Fallas

Arquitectura de microservicios con resiliencia aplicada para la materia de Sistemas Distribuidos.
Implementa mecanismos de tolerancia a fallas sobre un clúster multi-nodo de Minikube (Kubernetes)
y orquestación local con Docker Compose.

## Integrantes

- Jose Tixi
- Angel Cardenas
- Patricio Lucero

---

## Arquitectura

```
Cliente HTTP
     │
     ▼
┌─────────────────┐    ┌──────────────────────┐
│  API Gateway     │───▶│  Servicio Reservas   │
│  :8000           │    │  :8001               │
│  + Rate Limiter  │    │  + Circuit Breaker   │
│  + HTTP status   │    │  + Rollback          │
│  (5 req/s por IP)│    │  + Retries (Backoff) │
└─────────────────┘    │  + Fallback Silencioso│
     │                  └──────┬───────┬───────┘
     │                         │       │
     │                  ┌──────▼──┐ ┌───▼──────────┐
     │                  │Invent.  │ │ Pagos Stub   │
     │                  │:8002    │ │ :8003        │
     │                  │Redis/Lua│ │(Latencia 20s)│
     │                  └─────────┘ └──────────────┘
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
| API Gateway | 8000 | FastAPI + httpx + limits | Reservas |
| Servicio Reservas | 8001 | FastAPI + httpx + tenacity | Inventario, Pagos, Notificaciones |
| Servicio Inventario | 8002 | FastAPI + redis-py | Redis |
| Servicio Pagos (Stub) | 8003 | FastAPI | — |
| Servicio Notificaciones (Stub) | 8004 | FastAPI | — |
| Redis | 6379 | Redis 7 Alpine | — |

---

## Patrones de Resiliencia Implementados

### 1. Rate Limiter (API Gateway)

- **Ubicación:** `src/api_gateway/main.py`
- **Middleware** que limita a **5 peticiones/segundo por IP**
- Usa la librería `limits` con `MovingWindowRateLimiter` + `MemoryStorage`
- Responde **HTTP 429 (Too Many Requests)** cuando se excede el límite
- Conserva el **código HTTP real** que devuelve Reservas (`200`, `402`, `503`, etc.) para que la demo y k6 midan el resultado correcto

### 2. Circuit Breaker (Servicio Reservas → Pagos)

- **Ubicación:** `src/servicio_reservas/main.py` — clase `CircuitBreakerAsincrono`
- **Implementación propia** con `asyncio.Lock` para concurrencia segura
- **Estados:** CLOSED → OPEN (tras 3 fallos consecutivos) → HALF-OPEN (tras 30s de espera)
- **Timeout de 3s** en la llamada HTTP a Pagos para detectar latencia
- En estado OPEN rechaza la llamada al instante sin intentar conexión

### 3. Retry con Backoff Exponencial (Servicio Reservas → Inventario)

- **Ubicación:** `src/servicio_reservas/main.py` — decorador `@retry` de `tenacity`
- **3 intentos** máximo con backoff exponencial: 1s → 2s → 4s
- Filtrado: solo reintenta sobre `httpx.RequestError` y `httpx.HTTPStatusError`
- Captura caídas del pod de inventario (el ReplicaSet de K8s lo recrea automáticamente)

### 4. Fallback Silencioso (Servicio Reservas → Notificaciones)

- **Ubicación:** `src/servicio_reservas/main.py` — bloque `try/except` en el envío de notificaciones
- Si el stub de notificaciones falla (falla intencional ~50% del tiempo), la reserva **no se cancela**
- El usuario siempre recibe `{"status":"success"}` aunque el correo no se envíe
- El error se registra en logs pero no interrumpe el flujo principal

### 5. Rollback Condicional (Servicio Reservas)

- **Ubicación:** `src/servicio_reservas/main.py` — endpoint `crear_reserva()`
- Si el pago falla (timeout, error HTTP, Circuit Breaker abierto), se ejecuta automáticamente
  una llamada a `POST /inventario/devolver` para liberar el stock reservado
- Esto evita inconsistencias en Redis (stock debitado pero pago no concretado)

### 6. Descuento Atómico de Inventario (Servicio Inventario)

- **Ubicación:** `src/servicio_inventario/main.py` — `SCRIPT_DESCONTAR_ATOMICO`
- Usa un script Lua ejecutado dentro de Redis para hacer **validación de stock + descuento** como una sola operación atómica
- Evita que dos compras simultáneas del último asiento dejen el inventario en negativo
- Si no hay stock, responde `400` sin descontar; si el evento no existe, responde `404`

---

## Mapeo de los 6 Fallos de la Consigna

| Fallo | Mecanismo de inyección | Defensa implementada o propuesta |
|---|---|---|
| Inventario Fantasma | `kubectl delete pod` sobre un pod de `servicio-inventario` | Retry con backoff desde Reservas + recreación automática por ReplicaSet |
| Pasarela Lenta | `kubectl set env deployment/servicio-pagos-stub LATENCIA_ACTIVA=true` | Timeout de 3s + Circuit Breaker + rollback de inventario |
| Diluvio de Peticiones | k6 con 50 usuarios virtuales contra el API Gateway | Rate Limiter con HTTP 429 |
| Base de Datos Intermitente | NetworkPolicy, reinicio de Redis o corte temporal de conectividad hacia `redis` | Pendiente para análisis teórico/producción: Redis HA, Sentinel/Cluster, retries acotados e idempotencia |
| Correo Perdido | `kubectl scale deployment servicio-notificaciones --replicas=0` | Fallback silencioso: la compra no se cancela si falla Notificaciones |
| Condición de Carrera | Dos o más clientes comprando el último asiento al mismo tiempo | Descuento atómico en Redis con Lua |

---

## Requisitos

- **Windows 10/11** (el proyecto fue desarrollado y probado en Windows)
- **Docker Desktop** con integración WSL2 habilitada
- **Minikube** (para despliegue Kubernetes)
- **k6** (para pruebas de carga — opcional pero recomendado)
- **PowerShell 5.1+** (viene incluido en Windows)

### Instalación rápida de dependencias

```powershell
# Minikube (usar el instalador MSI desde https://minikube.sigs.k8s.io/docs/start/)
# Verificar instalación:
minikube version

# k6 (usando winget):
winget install k6

# Verificar:
k6 version
```

---

## Modo 1: Ejecución Local con Docker Compose

### Levantar todo

```powershell
docker compose up --build
```

Esto levanta los 6 servicios (5 microservicios + Redis). El API Gateway queda en `http://localhost:8000`.

### Probar flujo normal

```powershell
curl.exe -X POST http://localhost:8000/api/v1/comprar -H "Content-Type: application/json" -d "{\"evento_id\":\"evento_1\",\"cantidad\":1,\"usuario_email\":\"test@test.com\"}"
```

**Respuesta esperada:** `{"status":"success","message":"Reserva procesada con resiliencia de nivel de producción."}`

### Bajar todo

```powershell
docker compose down
```

---

## Modo 2: Ejecución en Minikube (Kubernetes)

### 1. Iniciar clúster multi-nodo

```powershell
minikube start --nodes=2 --cpus=4 --memory=4096
```

### 2. Construir imágenes localmente

```powershell
# Desde la raíz del proyecto:
docker compose build
```

### 3. Cargar imágenes a Minikube

```powershell
minikube image load api-gateway:latest
minikube image load servicio-reservas:latest
minikube image load servicio-inventario:latest
minikube image load servicio-pagos-stub:latest
minikube image load servicio-notificaciones-stub:latest
```

### 4. Desplegar manifests

```powershell
kubectl apply -f k8s-manifests/
```

Esto crea los recursos principales del sistema:
- 6 Deployments (API Gateway, Reservas, Inventario, Pagos, Notificaciones y Redis)
- 6 Services internos/externos, incluyendo `api-gateway` como `NodePort`
- 1 ConfigMap descriptivo de anti-affinity

### 5. Verificar que todo esté Running

```powershell
minikube kubectl -- get pods -o wide
```

Deben aparecer **8 pods** en estado `Running`. Los pods de `servicio-reservas` y `servicio-inventario`
tienen 2 réplicas cada uno, distribuidos en los 2 nodos.

### 6. Exponer el API Gateway

```powershell
minikube service api-gateway --url
```

Esto devuelve una URL tipo `http://127.0.0.1:XXXXX`. **Esa URL es el endpoint para todas las pruebas.**

### 7. Probar flujo normal en Minikube

```powershell
# Crear archivo temporal con el body JSON (solo una vez):
$body = '{"evento_id":"evento_1","cantidad":1,"usuario_email":"test@test.com"}'
Set-Content -Path "$env:TEMP\body.json" -Value $body -Encoding ASCII

# Probar:
curl.exe -X POST http://127.0.0.1:XXXXX/api/v1/comprar -H "Content-Type: application/json" -d "@$env:TEMP\body.json" --max-time 10
```

(Reemplazar `XXXXX` con el puerto que devolvió `minikube service`)

### 8. Limpiar

```powershell
kubectl delete -f k8s-manifests/
```

---

## Escenarios de Caos — Guía para la Presentación

Todos los escenarios asumen que el sistema está corriendo en Minikube con el API Gateway
expuesto via `minikube service api-gateway --url`. Se recomienda usar **2 terminales de PowerShell**.

### Preparación (solo una vez)

```powershell
# En cualquier terminal:
$body = '{"evento_id":"evento_1","cantidad":1,"usuario_email":"test@test.com"}'
Set-Content -Path "$env:TEMP\body.json" -Value $body -Encoding ASCII
$URL = "http://127.0.0.1:XXXXX/api/v1/comprar"
```

---

### ESCENARIO 1: El Inventario Fantasma (Caída de Pod)

**Qué prueba:** Retry con Backoff Exponencial + Recreación automática por ReplicaSet.

| Terminal 1 (Inyecta caos) | Terminal 2 (Prueba) |
|---|---|
| `minikube kubectl -- get pods -l app=servicio-inventario` | — |
| Anota el nombre del pod (ej: `servicio-inventario-xxxxx`) | — |
| `minikube kubectl -- delete pod servicio-inventario-xxxxx --now` | — |
| — | `curl.exe -X POST %URL% -H "Content-Type: application/json" -d "@$env:TEMP\body.json" --max-time 10` |
| — | Repite el curl cada ~3 segundos |
| `minikube kubectl -- get pods -l app=servicio-inventario -w` | — |

**Qué observar:**
1. El pod de inventario se elimina y pasa a `Terminating`
2. Los curls fallan con timeout (retries agotados) y mensaje de error controlado
3. Aprox. 15-20s después, un nuevo pod aparece con `AGE: 0s` (ReplicaSet lo recreó automáticamente)
4. Los curls vuelven a responder con éxito

**Resultado esperado:** ✅ El sistema no colapsa. El ReplicaSet garantiza alta disponibilidad del inventario.

---

### ESCENARIO 2: La Pasarela Lenta (Latencia + Circuit Breaker)

**Qué prueba:** Timeout → Rollback → Circuit Breaker se abre y corta peticiones futuras.

| Terminal 1 (Inyecta caos) | Terminal 2 (Prueba) |
|---|---|
| `minikube kubectl -- set env deployment/servicio-pagos-stub LATENCIA_ACTIVA=true` | — |
| Espera 5s a que el pod se reinicie con la variable | — |
| — | **Curl 1:** `curl.exe -X POST %URL% -H "Content-Type: application/json" -d "@$env:TEMP\body.json" --max-time 10` |
| — | **Curl 2 (inmediato):** mismo comando |
| — | **Curl 3 (inmediato):** mismo comando |
| `minikube kubectl -- set env deployment/servicio-pagos-stub LATENCIA_ACTIVA-` | — |

**Qué observar (Curl 1):**
- Tarda ~3 segundos (timeout)
- Responde con `{"message":"No se pudo procesar el pago. Stock liberado."}`
- El rollback liberó el stock automáticamente

**Qué observar (Curl 2 y 3):**
- Responden **al instante** (sub-100ms)
- El Circuit Breaker está en estado OPEN y corta sin intentar conexión
- El mensaje de error es inmediato, sin esperar timeouts

**Resultado esperado:** ✅ Circuit Breaker protege al sistema de llamadas innecesarias a un servicio lento. Rollback evita stock inconsistente.

---

### ESCENARIO 3: El Correo Perdido (Fallback Silencioso)

**Qué prueba:** El sistema tolera la caída total de un servicio no crítico (Notificaciones).

| Terminal 1 (Inyecta caos) | Terminal 2 (Prueba) |
|---|---|
| `minikube kubectl -- scale deployment servicio-notificaciones --replicas=0` | — |
| `minikube kubectl -- get pods -l app=servicio-notificaciones` (confirmar 0 pods) | — |
| — | `curl.exe -X POST %URL% -H "Content-Type: application/json" -d "@$env:TEMP\body.json" --max-time 10` |
| — | Repite el curl 2-3 veces para demostrar consistencia |
| `minikube kubectl -- scale deployment servicio-notificaciones --replicas=1` | — |

**Qué observar:**
- Todos los curls responden **`{"status":"success"}`** aunque notificaciones esté en 0
- El fallback silencioso captura el error y continúa
- La compra se completa: stock debitado, pago procesado, reserva confirmada
- La notificación simplemente se omite sin afectar al usuario

**Resultado esperado:** ✅ Servicio no crítico puede caer sin afectar la experiencia del usuario.

---

### ESCENARIO 4: El Diluvio (Prueba de Carga con k6)

**Qué prueba:** Rate Limiter bloquea tráfico excesivo con HTTP 429.

| Terminal única |
|---|
| `k6 run -e URL=http://127.0.0.1:XXXXX/api/v1/comprar tests-chaos\script-carga-k6.js` |

**Configuración de k6:**
- 50 VUs (usuarios virtuales concurrentes)
- Duración: 10 segundos
- Check: `r.status === 200 || r.status === 429`
- Sleep de 100ms entre iteraciones

**Qué observar en la salida de k6:**
```
checks_total.......: ~4500    450/s
checks_succeeded...: 100.00%  (~4500 de ~4500)
checks_failed......: 0.00%    0 de ~4500
```

Aunque la mayoría de respuestas sean 429 (Rate Limited), el check pasa porque 429 es válido.
Las ~50-100 requests que pasan el Rate Limiter reciben 200 y completan la reserva.

**Resultado esperado:** ✅ Rate Limiter protege el sistema de sobrecarga. 0% de errores inesperados.

---

### ESCENARIO 5: Caos Automatizado (Script Todo-en-Uno)

Para una demostración rápida sin cambiar de terminal:

```powershell
.\tests-chaos\escenarios-caos.ps1
```

**Nota:** Este script ejecuta los 4 escenarios en secuencia. Los `Read-Host` pausan
para que puedas probar manualmente. Si se ejecuta en modo no interactivo, los caos
se inyectan y restauran inmediatamente — útil solo para validar que los comandos funcionan.

---

## Solución de Problemas Frecuentes

### El túnel de Minikube expiró

```powershell
# El puerto 62755 (o cualquier otro) dejó de funcionar.
# Simplemente obtén uno nuevo:
minikube service api-gateway --url
# Actualiza la variable:
$URL = "http://127.0.0.1:NUEVOPUERTO/api/v1/comprar"
```

### Los pods están en ImagePullBackOff o ErrImagePull

```powershell
# Las imágenes no se cargaron correctamente. Recarga:
minikube image load api-gateway:latest
minikube image load servicio-reservas:latest
minikube image load servicio-inventario:latest
minikube image load servicio-pagos-stub:latest
minikube image load servicio-notificaciones-stub:latest
# Luego borra los pods para que se recrean:
kubectl delete pods --all
```

### k6 no encuentra el script

```powershell
# Usa la ruta absoluta:
k6 run -e URL=http://127.0.0.1:XXXXX/api/v1/comprar "C:\ruta\completa\al\proyecto\tests-chaos\script-carga-k6.js"
```

### Invoke-WebRequest no funciona (modo no interactivo)

El comando `curl` en PowerShell es un alias de `Invoke-WebRequest` que no funciona
en ciertos contextos. Usa siempre `curl.exe` (el verdadero curl) para hacer requests HTTP.

### Error CRLF en scripts .sh

Si ves `$'\r': command not found` al ejecutar un script bash, es porque fue creado en Windows.
Convierte a LF Unix:
```powershell
$path = "tests-chaos\escenarios-caos.sh"
$content = Get-Content $path -Raw
$unix = $content -replace "`r`n", "`n"
[System.IO.File]::WriteAllText((Resolve-Path $path), $unix, [System.Text.Encoding]::UTF8)
```

O mejor, usa directamente el script `.ps1` (PowerShell) que ya está preparado.

---

## Estructura del Proyecto

```
/
├── docker-compose.yml               # Orquestación local (Docker Compose)
├── README.md                        # Este archivo
├── src/
│   ├── api_gateway/
│   │   ├── main.py                  # FastAPI + Rate Limiter + preservación de códigos HTTP
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── servicio_reservas/
│   │   ├── main.py                  # Circuit Breaker + Retries + Fallback + Rollback
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── servicio_inventario/
│   │   ├── main.py                  # Inventario Redis + descuento atómico con Lua
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── servicio_pagos_stub/
│   │   ├── main.py                  # Stub con latencia condicional (LATENCIA_ACTIVA)
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── servicio_notificaciones_stub/
│       ├── main.py                  # Stub con falla intermitente (~50%)
│       ├── requirements.txt
│       └── Dockerfile
├── k8s-manifests/                   # Manifiestos para Kubernetes
│   ├── api-gateway.yaml
│   ├── servicio-reservas.yaml
│   ├── servicio-inventario.yaml
│   ├── servicio-pagos.yaml
│   ├── servicio-notificaciones.yaml
│   ├── redis.yaml
│   └── anti-affinity-policies.yaml
├── tests-chaos/                     # Pruebas de caos
│   ├── escenarios-caos.ps1          # Script automatizado (PowerShell)
│   ├── escenarios-caos.sh           # Script automatizado (Bash — requiere ajustes en Windows)
│   └── script-carga-k6.js           # Prueba de carga con k6 (50 VUs, 10s)
```

---

## Referencias Técnicas

- **FastAPI** — Framework web asíncrono para los microservicios
- **httpx** — Cliente HTTP asíncrono para comunicación entre servicios
- **tenacity** — Librería de retries con backoff exponencial
- **limits** — Rate limiting con Moving Window
- **Redis** — Almacenamiento en memoria para el inventario
- **Minikube** — Kubernetes local multi-nodo
- **k6** — Herramienta de pruebas de carga
