# Guion de Demo en Vivo — Sistema de Reservas de Entradas

Duración estimada: 12-13 minutos. Dani hace introducción + Fallos 1 y 2.
Jose hace Fallos 3 y 4 + cierre.

---

## PARTE A — Preparación de cada máquina (15-20 min antes de empezar, sin público)

### Paso 1 (ambos) — Confirmar la IP real de la máquina

**No usar `localhost` para ningún curl** — se descubrió que en este entorno WSL2
`localhost` puede fallar con timeouts largos. Usar siempre la IP real de la red
en la que estén conectados ese día (universidad, datos móviles, etc.).

Dani:
```bash
ip addr show eth1 | grep "inet "
```

Jose:
```bash
ip a | grep "inet " | grep -v 127.0.0.1
```

Anotar la IP que aparezca (ejemplo: `192.168.18.53` para Dani, `192.168.18.130`
para Jose). Estas van a cambiar según la red del día — repetir este paso apenas
lleguen al lugar de la presentación, antes de cualquier otra cosa.

### Paso 2 (ambos) — Verificar que Tailscale está sano

```bash
sudo tailscale status
```

Debe mostrar ambas máquinas con `active; direct ...` (no debe decir `relay`).

**Si algo se ve raro, lento, o hay timeouts**: el arreglo que funcionó fue reiniciar
Tailscale:
```bash
sudo tailscale down
sleep 3
sudo tailscale up
sleep 5
```

### Paso 3 (ambos) — Verificar que los 2 nodos están Ready

Dani:
```bash
sudo k3s kubectl get nodes
```

Jose:
```bash
kubectl get nodes
```

Ambos deben decir `Ready`. Si `daft` (nodo de Jose) aparece `NotReady`:
```bash
sudo systemctl restart k3s-agent
sleep 15
kubectl get nodes
```

### Paso 4 (Dani) — Verificar que los 7 pods están sanos

```bash
sudo k3s kubectl get pods -o wide
```

Deben aparecer 7 pods, todos `1/1 Running`: gateway, reservas, pagos-stub,
notificaciones-stub, postgres, y 2 de inventario (uno en cada nodo). Si alguno
está `Pending` o `Terminating` desde hace rato, forzar su eliminación:
```bash
sudo k3s kubectl delete pod <nombre-del-pod> --force --grace-period=0
```

### Paso 5 (Dani) — Resetear el inventario a un número alto

```bash
sudo k3s kubectl exec -it deploy/postgres -- psql -U ticketuser -d ticketsdb -c "UPDATE seats SET available = 30 WHERE event_id = 'concierto-2026';"
```

### Paso 6 (Dani) — Probar que una compra normal funciona ANTES de tener público

```bash
curl -X POST "http://<IP-DE-DANI>:30080/purchase?event_id=concierto-2026&email=demo@example.com&amount=15"
```

Debe devolver un JSON con `"purchase_status":"completed"`. Si da
`"Failed to connect"` o timeout, reiniciar k3s:
```bash
sudo systemctl restart k3s
sleep 20
```
Y volver a probar.

### Paso 7 (Jose) — Dejar corriendo la vista en vivo de los pods

En una segunda ventana de terminal, Jose deja esto corriendo TODO el tiempo
durante la demo (esto es lo que el público va a ver en su pantalla):

```bash
watch -n 2 'kubectl get pods -o wide'
```

---

## PARTE B — Guion de la demo (con público)

### Minuto 0-2 — Introducción (Dani)

```bash
sudo k3s kubectl get nodes -o wide
```

**Decir:**
> "Tenemos un clúster de Kubernetes real, con 2 nodos: cada uno es literalmente
> una computadora física distinta, la mía y la de mi compañero, conectadas entre
> sí mediante una red privada llamada Tailscale, aunque estemos en redes distintas."

```bash
sudo k3s kubectl get pods -o wide
```

**Decir:**
> "Aquí se ven los 7 pods corriendo — un pod es la unidad más pequeña donde vive
> cada uno de nuestros servicios. Fíjense que las 2 réplicas de Inventario están
> en nodos distintos: una en mi máquina, otra en la de José. Esto lo forzamos a
> propósito para que si un nodo se cae, el servicio siga funcionando."

---

### Minuto 2-3 — Compra exitosa, el "camino feliz" (Dani)

```bash
curl -X POST "http://<IP-DE-DANI>:30080/purchase?event_id=concierto-2026&email=demo@example.com&amount=15"
```

**Salida esperada (aprox.):**
```json
{"event_id":"concierto-2026","steps":{"inventario":{"reserved":true,"remaining":29},"pago":{"status":"approved"},"notificacion":{"status":"sent"}},"purchase_status":"completed"}
```

**Decir:**
> "Así se ve una compra normal: el sistema reserva el asiento, cobra el pago, y
> envía la confirmación. Todo en una sola llamada, pasando por 5 servicios
> distintos repartidos entre los 2 nodos."

*(Nota: a veces el paso de "notificacion" sale como "failed_fallback" en vez de
"sent" — es normal, el stub tiene una probabilidad aleatoria de fallo. Si pasa,
decir: "aquí ya se ve de forma natural nuestro mecanismo de Fallback, que vamos
a explicar más adelante".)*

---

### Minuto 3-6 — Fallo 1: Inventario Fantasma (Dani)

```bash
sudo k3s kubectl get pods -o wide | grep inventario
```

Anotar los 2 nombres exactos que salgan.

**Decir antes de ejecutar:**
> "Ahora vamos a simular que el Servicio de Inventario se cae por completo —
> vamos a borrar sus 2 réplicas al mismo tiempo, en pleno funcionamiento."

```bash
sudo k3s kubectl delete pod <nombre-pod-1> <nombre-pod-2> &
curl -X POST "http://<IP-DE-DANI>:30080/purchase?event_id=concierto-2026&email=demo@example.com&amount=15"
```

**Decir mientras se espera la respuesta:**
> "Acabamos de destruir las 2 réplicas de Inventario. Kubernetes está
> recreándolas ahora mismo, mientras nuestro código espera pacientemente con un
> mecanismo llamado 'Retry con backoff exponencial' — esto significa
> 'reintentar, pero esperando cada vez un poco más entre intento e intento' (1
> segundo, luego 2, luego 4, hasta 8). Así le damos tiempo real a que el pod se
> recupere antes de rendirnos."

**Cuando llegue la respuesta exitosa:**
> "Y aquí está: la compra se completó de todas formas, a pesar de haber
> destruido por completo el servicio de inventario."

---

### Minuto 6-8 — Fallo 2: Pasarela Lenta (Dani)

```bash
sudo k3s kubectl run demo-slow --image=curlimages/curl --restart=Never -- curl -X POST "http://pagos-stub:8000/chaos/slow-mode?enabled=true&delay_seconds=20"
sleep 15
sudo k3s kubectl logs demo-slow
sudo k3s kubectl delete pod demo-slow
```

**Decir:**
> "Ahora activamos un modo especial en el Servicio de Pagos que hace que tarde
> 20 segundos en responder cada vez — simulando que la pasarela de pago está
> sobrecargada."

Repetir esto 3 veces seguidas:
```bash
time curl -X POST "http://<IP-DE-DANI>:30080/purchase?event_id=concierto-2026&email=demo@example.com&amount=15"
```

**Decir después del 3er intento (cuando salga "circuit breaker abierto"):**
> "Fíjense que cada intento tardó solo unos segundos, no 20 — porque
> configuramos un tiempo límite corto. Después de 3 fallos seguidos, se activó
> un 'Circuit Breaker' (interruptor de circuito): funciona como el interruptor
> eléctrico de una casa — si detecta un problema repetido, 'corta la corriente'
> para evitar que el problema se propague. A partir de ahora, el sistema ya no
> intenta llamar a Pagos en absoluto, falla al instante con un mensaje claro, en
> vez de hacer esperar al usuario 20 segundos por cada intento."

**Desactivar el modo lento antes de seguir:**
```bash
sudo k3s kubectl run demo-slow-off --image=curlimages/curl --restart=Never -- curl -X POST "http://pagos-stub:8000/chaos/slow-mode?enabled=false"
sleep 15
sudo k3s kubectl logs demo-slow-off
sudo k3s kubectl delete pod demo-slow-off
```

---

### Minuto 8-10 — Fallo 3: Diluvio de Peticiones (Jose)

```bash
kubectl exec -it deploy/postgres -- psql -U ticketuser -d ticketsdb -c "UPDATE seats SET available = 30 WHERE event_id = 'concierto-2026';"
```

**Decir:**
> "Ahora simulamos algo distinto: un pico repentino de tráfico, como cuando se
> abre la preventa de un concierto muy popular y muchas personas entran al
> mismo tiempo."

```bash
kubectl run load-demo --image=curlimages/curl --restart=Never -- sh -c 'i=0; while [ $i -lt 15 ]; do curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "http://gateway:8000/purchase?event_id=concierto-2026&email=demo@example.com&amount=15" & i=$((i+1)); done; wait'
sleep 15
kubectl logs load-demo
```

**Salida esperada:** una mezcla de líneas `HTTP 200` y `HTTP 503` (aprox. 9 y 6).

**Decir:**
> "Mandamos 15 compras exactamente al mismo tiempo. Nuestro Gateway tiene un
> límite de 10 peticiones simultáneas — a esto se le llama 'Bulkhead' (mampara),
> como los compartimentos estancos de un barco: si uno se inunda, el resto del
> barco sigue flotando. Vean que 9 peticiones se procesaron bien (código 200),
> y 6 se rechazaron rápido (código 503) en vez de dejar que todo el sistema se
> sature."

```bash
kubectl delete pod load-demo
```

---

### Minuto 10-12 — Fallo 4: Correo Perdido (Jose)

```bash
kubectl run demo-down --image=curlimages/curl --restart=Never -- curl -X POST "http://notificaciones-stub:8000/chaos/down-mode?enabled=true"
sleep 15
kubectl logs demo-down
kubectl delete pod demo-down
```

**Decir:**
> "Ahora apagamos por completo el Servicio de Notificaciones — el que manda el
> correo de confirmación."

```bash
curl -X POST "http://<IP-DE-JOSE>:30080/purchase?event_id=concierto-2026&email=demo@example.com&amount=15"
```

*(Si por casualidad el paso de "pago" falla en vez de "notificacion" — el stub
de Pagos tiene su propia probabilidad de error aleatoria, independiente de este
fallo — simplemente repetir el comando una vez más.)*

**Decir cuando salga el resultado correcto:**
> "Fíjense en el resultado: el asiento se reservó, el pago se aprobó, y la
> compra se marca como 'completed' — solo el paso de notificación aparece
> marcado como fallido. A esto se le llama 'Fallback' (alternativa de
> respaldo): como el correo no es algo crítico —el usuario ya tiene su entrada
> pagada—, en vez de cancelar toda la compra por ese detalle, seguimos adelante
> y solo dejamos anotado que el correo se debe reintentar después."

```bash
kubectl run demo-down-off --image=curlimages/curl --restart=Never -- curl -X POST "http://notificaciones-stub:8000/chaos/down-mode?enabled=false"
sleep 15
kubectl logs demo-down-off
kubectl delete pod demo-down-off
```

---

### Minuto 12-13 — Cierre (ambos)

**Decir:**
> "Con esto mostramos los 4 mecanismos de resiliencia funcionando en vivo,
> sobre nuestra infraestructura real de 2 nodos. Los otros 2 fallos del
> catálogo —Base de Datos Intermitente y Condición de Carrera— los analizamos
> a profundidad en el informe teórico, con su fundamento en el teorema CAP y
> en modelos de concurrencia."

---

## PARTE C — Plan B si algo falla en vivo

- **Si un curl da timeout o "No route to host":** revisar que están usando la
  IP correcta (no `localhost`) y que dijeron la IP del día correcto.
- **Si Tailscale se ve lento/inestable:** `sudo tailscale down && sudo tailscale up`
  en la máquina afectada, esperar 10 segundos, reintentar.
- **Si un nodo aparece NotReady:** `sudo systemctl restart k3s-agent` (en la
  máquina de Jose) o `sudo systemctl restart k3s` (en la de Dani), esperar 20s.
- **Si un pod queda en Pending/Terminating sin resolverse:**
  `kubectl delete pod <nombre> --force --grace-period=0`
- **Si el paso de Pagos o Notificaciones falla "por accidente" en un fallo que
  no es el suyo:** es el 15%/20% de probabilidad de fallo aleatorio programado
  en los stubs — simplemente repetir el comando de compra una vez más.
