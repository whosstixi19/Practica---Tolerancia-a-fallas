from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import httpx
import time
import asyncio
from contextlib import asynccontextmanager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

http_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient()
    yield
    await http_client.aclose()

app = FastAPI(title="Servicio de Reservas - Capa Resiliencia Producción Total", lifespan=lifespan)

INVENTARIO_URL = "http://servicio-inventario:8002"
PAGOS_URL = "http://servicio-pagos-stub:8003"
NOTIFICACIONES_URL = "http://servicio-notificaciones-stub:8004"


class CircuitBreakerAsincrono:
    def __init__(self, fail_max=3, reset_timeout=30):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.estado = "CLOSED"
        self.fallos_consecutivos = 0
        self.tiempo_proximo_intento = 0
        self._lock = asyncio.Lock()

    async def verificar_estado(self):
        async with self._lock:
            if self.estado == "OPEN":
                if time.time() > self.tiempo_proximo_intento:
                    self.estado = "HALF-OPEN"
                    print(f"[CIRCUIT BREAKER] Cambiando a HALF-OPEN de forma segura.")
                else:
                    raise HTTPException(status_code=503, detail="Circuito ABIERTO temporalmente por fallos.")

    async def registrar_exito(self):
        async with self._lock:
            self.fallos_consecutivos = 0
            self.estado = "CLOSED"

    async def registrar_fallo(self):
        async with self._lock:
            self.fallos_consecutivos += 1
            print(f"[CIRCUIT BREAKER] Fallo. Consecutivos: {self.fallos_consecutivos}/{self.fail_max}")
            if self.fallos_consecutivos >= self.fail_max or self.estado == "HALF-OPEN":
                self.estado = "OPEN"
                self.tiempo_proximo_intento = time.time() + self.reset_timeout
                print(f"[CIRCUIT BREAKER] Circuito abierto por {self.reset_timeout}s.")


inventario_breaker = CircuitBreakerAsincrono(fail_max=3, reset_timeout=30)
pagos_breaker = CircuitBreakerAsincrono(fail_max=3, reset_timeout=30)


@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=1, min=1, max=4), 
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    reraise=True
)
async def llamar_inventario_seguro(payload: dict):
    await inventario_breaker.verificar_estado()
        
    try:
        response = await http_client.post(f"{INVENTARIO_URL}/inventario/descontar", json=payload, timeout=2.0)
        
        if response.status_code >= 500:
            await inventario_breaker.registrar_fallo()
            response.raise_for_status()
            
        if response.status_code == 200:
            await inventario_breaker.registrar_exito()
            
        return response
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        await inventario_breaker.registrar_fallo()
        raise exc


@app.post("/reservas")
async def crear_reserva(payload: dict):
    inventario_ok = False

    try:
        inv_res = await llamar_inventario_seguro(payload)
        if inv_res.status_code == 200:
            inventario_ok = True
        else:
            raise HTTPException(status_code=400, detail="Sin asientos disponibles.")
    except Exception:
        raise HTTPException(status_code=503, detail="Servicio de Inventario no disponible transitoriamente.")

    cantidad_asientos = payload.get("cantidad", 1)
    monto_calculado = 25.0 * cantidad_asientos

    pago_exitoso = False
    
    try:
        await pagos_breaker.verificar_estado()
        
        try:
            pago_res = await http_client.post(f"{PAGOS_URL}/pagar", json={"monto": monto_calculado}, timeout=3.0)
            if pago_res.status_code == 200:
                pago_exitoso = True
                await pagos_breaker.registrar_exito()
            else:
                await pagos_breaker.registrar_fallo()
                print("[PAGOS] Cobro denegado por la entidad financiera.")
        except (httpx.TimeoutException, httpx.RequestError):
            await pagos_breaker.registrar_fallo()
            print(f"[REMEDIACIÓN] Timeout en pagos. Activando mitigación.")
            
    except HTTPException as e:
        print(f"[CIRCUITO BLOQUEADO] {e.detail}")

    if not pago_exitoso and inventario_ok:
        print("[ROLLBACK] Liberando asientos en Redis debido a fallas en el pago.")
        await http_client.post(f"{INVENTARIO_URL}/inventario/devolver", json=payload)
        return JSONResponse(status_code=402, content={"message": "No se pudo procesar el pago. Stock liberado."})

    try:
        payload_notificacion = {
            "email": payload.get("usuario_email", "correo.default@est.ups.edu.ec"),
            "mensaje": f"Confirmación de compra exitosa para el evento: {payload.get('evento_id')}."
        }
        await http_client.post(f"{NOTIFICACIONES_URL}/notificar", json=payload_notificacion, timeout=1.0)
    except httpx.RequestError:
        print("[FALLBACK NOTIFICACIONES] Pod de correos offline. Transacción completada con éxito.")

    return {"status": "success", "message": "Reserva procesada con resiliencia de nivel de producción."}
