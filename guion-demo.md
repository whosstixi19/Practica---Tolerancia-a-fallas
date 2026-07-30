# Guion de Demo — Tolerancia a Fallas (k3s + Tailscale)

**Duración:** 10–12 minutos
**Integrantes:** Jose Tixi (A), Angel Cardenas (B), Patricio Lucero (C)
**Infraestructura:** k3s multi-nodo (2 PCs físicas), Tailscale, Docker Hub
**API Gateway:** `http://100.70.227.75:30000` (Tailscale IP de tixilegion, NodePort 30000)

---

## Setup Inicial (antes de la demo, 5 min)

En PC1 (tixilegion), terminal Ubuntu WSL:
```bash
cd /mnt/c/Users/tixi4/Documents/Universidad/5to/SD/Practica\ -\ Tolerancia\ a\ fallas

# Probar que el sistema responde
URL_BASE="http://100.70.227.75:30000"
curl -X POST "$URL_BASE/api/v1/comprar" \
  -H "Content-Type: application/json" \
  -d '{"evento_id":"evento_1","cantidad":1,"usuario_email":"demo@test.com"}'
# Debe responder: {"status":"success","message":"Reserva procesada con resiliencia de nivel de producción."}
```

En PC2 (desktop-gmjr8l6), terminal Ubuntu WSL:
```bash
cd /mnt/c/Users/tixi4/Documents/Universidad/5to/SD/Practica\ -\ Tolerancia\ a\ fallas
# Probar que tambien llega desde PC2
curl -X POST "http://100.70.227.75:30000/api/v1/comprar" \
  -H "Content-Type: application/json" \
  -d '{"evento_id":"evento_1","cantidad":1,"usuario_email":"demo@test.com"}'
```

---

## Persona A — Jose Tixi (Apertura + CAOS 1 + Cierre)

### Apertura (0:00 – 2:00)

| Tiempo | Qué decir / Hacer | Comando |
|--------|-------------------|---------|
| 0:00 | "Buenos días. Vamos a demostrar un sistema de reservas con 5 patrones de tolerancia a fallas sobre un clúster Kubernetes real de 2 máquinas físicas." | — |
| 0:20 | Mostrar los 2 nodos físicos | `sudo kubectl get nodes -o wide` |
| 0:35 | "Tenemos tixilegion (control-plane) y desktop-gmjr8l6 (worker). Están conectados por Tailscale, una VPN basada en WireGuard." | — |
| 0:50 | Mostrar todos los pods Running | `sudo kubectl get pods -o wide` |
| 1:05 | "8 pods distribuidos en ambos nodos. Reservas e inventario tienen 2 réplicas cada uno con anti-affinity: Kubernetes obliga a que cada réplica esté en un nodo distinto." | — |
| 1:25 | Explicar el flujo: "Cliente → API Gateway (Rate Limiter: 5 req/s) → Servicio Reservas (Circuit Breaker + Retry + Fallback) → Inventario (Redis), Pagos Stub, Notificaciones Stub" | — |
| 1:45 | "Cada patrón protege contra un tipo de fallo distinto. Vamos a verlos en acción." | — |

### CAOS 1 — El Inventario Fantasma (2:00 – 4:00)
**Patrón: Retry con Backoff Exponencial + ReplicaSet**

**Qué hace el programa:** El `servicio-reservas` llama a `servicio-inventario` para descontar asientos. Usa `@retry` de la librería `tenacity` con 3 intentos y espera exponencial (1s → 2s → 4s). Si todos fallan, responde 503. Mientras tanto, el ReplicaSet de K8s recrea automáticamente el pod muerto.

| Tiempo | Qué decir / Hacer | Comando |
|--------|-------------------|---------|
| 2:00 | "Primer escenario: matamos un pod de inventario en vivo para simular una caída. El sistema debe reintentar y recuperarse." | — |
| 2:10 | Localizar el pod de inventario | `POD_INV=$(sudo kubectl get pods -l app=servicio-inventario -o jsonpath="{.items[0].metadata.name}") && echo $POD_INV` |
| 2:20 | "Angel, lanza un curl justo después de que elimine el pod." | — |
| 2:25 | Eliminar el pod | `sudo kubectl delete pod $POD_INV --now` |
| 2:30 | **Angel ejecuta curl** (ver sección de Angel) | — |
| 2:45 | "Ese curl falló con timeout. Pero el ReplicaSet ya está creando un reemplazo." | `sudo kubectl get pods -l app=servicio-inventario -w` |
| 3:00 | "En 15-20 segundos el pod nuevo estará Running." | — |
| 3:15 | "Angel, lanza otro curl ahora." | — |
| 3:20 | **Angel ejecuta curl** | — |
| 3:30 | "Respondió 200. El Retry con Backoff + ReplicaSet funcionaron: el sistema se auto-recuperó." | — |
| 3:45 | **Transición:** "Eso fue el Retry. Ahora Angel muestra el Circuit Breaker con la pasarela de pagos lenta." | — |

---

## Persona B — Angel Cardenas (CAOS 2 + Curls de validación)

### CAOS 2 — La Pasarela Lenta (4:00 – 7:00)
**Patrón: Circuit Breaker + Rollback Condicional**

**Qué hace el programa:** El `servicio-reservas` tiene un `CircuitBreakerAsincrono` (implementación propia con `asyncio.Lock`) que monitorea las llamadas a `servicio-pagos-stub`. Si hay 3 fallos consecutivos, el circuito se abre (OPEN) por 30 segundos y rechaza llamadas al instante sin intentar conexión. Además, si el pago falla pero el inventario ya se descontó, se ejecuta un rollback automático (`POST /inventario/devolver`) para liberar el stock.

| Tiempo | Qué decir / Hacer | Comando |
|--------|-------------------|---------|
| 4:00 | "Segundo escenario: activamos latencia extrema en pagos para probar el Circuit Breaker y el Rollback." | — |
| 4:10 | Explicar: "El Circuit Breaker tiene 3 estados: CLOSED (normal), OPEN (corta llamadas), HALF-OPEN (prueba si ya se recuperó)" | — |
| 4:25 | Activar latencia de 20s | `sudo kubectl set env deployment/servicio-pagos-stub LATENCIA_ACTIVA=true` |
| 4:35 | "El pod de pagos se reiniciará con la nueva variable." | `sudo kubectl get pods -l app=servicio-pagos-stub` |
| 4:45 | **Curl 1 (lento — ~3s):** Tarda porque hace timeout a los 3s. Luego hace rollback liberando el stock. | `curl -X POST "http://100.70.227.75:30000/api/v1/comprar" -H "Content-Type: application/json" -d '{"evento_id":"evento_1","cantidad":1,"usuario_email":"demo@test.com"}' --max-time 10` |
| 5:00 | "Tardó ~3 segundos — fue el timeout. El sistema intentó pagar, falló, e hizo rollback: liberó el asiento en Redis automáticamente." | — |
| 5:15 | "El Circuit Breaker detectó el fallo. Van 1. Necesita 3 para abrirse." | — |
| 5:20 | **Curl 2 (rápido — instantáneo):** | mismo curl |
| 5:30 | "Van 2 fallos. El breaker sigue contando." | — |
| 5:35 | **Curl 3 (rápido — instantáneo):** | mismo curl |
| 5:45 | "¡Tercer fallo! El Circuit Breaker pasó a OPEN. A partir de ahora, cualquier llamada a pagos se rechaza al instante, sin siquiera intentar conectar." | — |
| 5:55 | **Curl 4 (instantáneo — cortado por el breaker):** | mismo curl |
| 6:05 | "Respondió al instante — el breaker cortó antes de intentar. El sistema ya no malgasta recursos." | — |
| 6:15 | Restaurar pagos a normalidad | `sudo kubectl set env deployment/servicio-pagos-stub LATENCIA_ACTIVA-` |
| 6:30 | **Transición:** "Eso fue el Circuit Breaker con Rollback. Ahora Patricio muestra cómo toleramos la caída total de notificaciones." | — |

---

## Persona C — Patricio Lucero (CAOS 3 + CAOS 4)

### CAOS 3 — El Correo Perdido (7:00 – 8:30)
**Patrón: Fallback Silencioso**

**Qué hace el programa:** El `servicio-reservas` envía la notificación en un bloque `try/except`. Si la llamada a `servicio-notificaciones-stub` falla (el stub tiene `FALLA_INTERMITENTE=true` y falla ~50% de las veces), el error se captura, se registra en logs, y la reserva continúa. El usuario siempre recibe `{"status":"success"}` aunque el correo no se envíe.

| Tiempo | Qué decir / Hacer | Comando |
|--------|-------------------|---------|
| 7:00 | "Tercer escenario: vamos a cargar por completo el servicio de notificaciones para demostrar el Fallback Silencioso." | — |
| 7:10 | Explicar: "Las notificaciones no son críticas para la compra. Si caen, la reserva sigue adelante." | — |
| 7:20 | Escalar notificaciones a 0 réplicas | `sudo kubectl scale deployment servicio-notificaciones --replicas=0` |
| 7:30 | Confirmar que quedó en 0 | `sudo kubectl get pods -l app=servicio-notificaciones` |
| 7:35 | **Curl 1:** | `curl -X POST "http://100.70.227.75:30000/api/v1/comprar" -H "Content-Type: application/json" -d '{"evento_id":"evento_1","cantidad":1,"usuario_email":"demo@test.com"}'` |
| 7:45 | "Status 200 — la reserva se procesó con éxito aunque notificaciones esté caído. El fallback capturó el error y siguió." | — |
| 7:50 | **Curl 2:** | mismo curl |
| 8:00 | "Otro 200. Demostrado: un servicio no crítico puede caer sin afectar al usuario." | — |
| 8:10 | Restaurar notificaciones | `sudo kubectl scale deployment servicio-notificaciones --replicas=1` |
| 8:20 | **Transición:** "Finalmente, veamos cómo el Rate Limiter protege contra sobrecarga." | — |

### CAOS 4 — El Diluvio (8:30 – 10:30)
**Patrón: Rate Limiter**

**Qué hace el programa:** El API Gateway tiene un middleware con `MovingWindowRateLimiter` de la librería `limits` que permite máximo 5 peticiones por segundo por IP. Cuando se excede, responde HTTP 429 (Too Many Requests). k6 dispara 50 usuarios virtuales concurrentes durante 10 segundos. La mayoría recibe 429, algunos reciben 200. Nunca hay errores inesperados.

| Tiempo | Qué decir / Hacer | Comando |
|--------|-------------------|---------|
| 8:30 | "Último escenario: saturación con 50 usuarios concurrentes durante 10 segundos usando k6." | — |
| 8:40 | Explicar: "El Rate Limiter del Gateway permite 5 peticiones/segundo por IP. Con 50 VUs, la mayoría recibirá 429." | — |
| 8:50 | Ejecutar k6 | `k6 run tests-chaos/script-carga-k6.js` |
| 9:00 | *(Esperar 10s mientras k6 corre)* | — |
| 9:10 | *(k6 termina)* | — |
| 9:15 | Señalar en la salida: `checks_succeeded: 100.00%` | — |
| 9:25 | "Todas las respuestas fueron 200 (éxito) o 429 (Rate Limited). El 100% de los checks pasaron." | — |
| 9:35 | "El Rate Limiter protegió a los servicios internos de la sobrecarga." | — |
| 9:45 | "Ninguna petición causó un error inesperado — solo respuestas controladas." | — |
| 10:00 | "Con esto demostramos los 5 patrones de resiliencia funcionando en k3s real con 2 máquinas físicas." | — |

---

## Persona A — Jose Tixi (Cierre — 10:30 en adelante)

| Tiempo | Qué decir / Hacer | Comando |
|--------|-------------------|---------|
| 10:30 | "Resumen de lo que demostramos:" | — |
| 10:35 | "1. **Retry Exponencial** — el pod de inventario muerto se reintentó 3 veces (1s, 2s, 4s) y el ReplicaSet lo recreó automáticamente." | — |
| 10:45 | "2. **Circuit Breaker** — latencia en pagos (20s) activó el estado OPEN tras 3 fallos, cortando peticiones al instante." | — |
| 10:55 | "3. **Rollback Condicional** — cuando el pago falló, el stock se liberó automáticamente vía POST /inventario/devolver." | — |
| 11:05 | "4. **Fallback Silencioso** — notificaciones escalado a 0, la reserva se completó igual." | — |
| 11:15 | "5. **Rate Limiter** — k6 disparó 50 VUs y el Gateway respondió 429 sin colapsar." | — |
| 11:25 | Mostrar pods finales — todos Running | `sudo kubectl get pods -o wide` |
| 11:35 | "El sistema se recuperó completamente. Todos los pods están Running y distribuidos en ambos nodos." | — |
| 11:45 | "Conclusión: el sistema tolera fallos de red, latencia extrema, caída de pods y sobrecarga sin errores al usuario, sobre infraestructura real de 2 computadoras físicas." | — |

---

## Resumen de Escenarios

| Escenario | Patrón | Persona | Fallo inyectado | Comportamiento observado |
|-----------|--------|---------|-----------------|--------------------------|
| 1. Inventario Fantasma | Retry + ReplicaSet | A | Pod eliminado | Timeouts durante recreación, luego recuperación automática |
| 2. Pasarela Lenta | Circuit Breaker + Rollback | B | Latencia 20s en pagos | 1er curl timeout + rollback, 2do-4to instantáneos (OPEN) |
| 3. Correo Perdido | Fallback Silencioso | C | Notificaciones escala 0 | Reservas exitosas aunque notificaciones caídas |
| 4. Diluvio | Rate Limiter | C | 50 VUs k6 | 100% checks (200 + 429), sin errores inesperados |

---

## Checklist Pre-Demo
- [ ] `sudo kubectl get nodes` — 2 nodos Ready
- [ ] `sudo kubectl get pods` — todos Running
- [ ] Curl de prueba responde 200
- [ ] `k6 version` — instalado en PC1
- [ ] Tailscale activo en ambas PCs: `tailscale status`
