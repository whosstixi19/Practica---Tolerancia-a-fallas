from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os

app = FastAPI(title="Servicio de Reservas")

# Direcciones de red de los otros servicios (configurables para Kubernetes)
INVENTARIO_URL = os.getenv("INVENTARIO_URL", "http://localhost:8002")
PAGOS_URL = os.getenv("PAGOS_URL", "http://localhost:8003")
NOTIFICACIONES_URL = os.getenv("NOTIFICACIONES_URL", "http://localhost:8004")

class ReservaRequest(BaseModel):
    evento_id: str
    cantidad: int
    usuario_email: str

@app.post("/reservas")
async def crear_reserva(reserva: ReservaRequest):
    payload = {"evento_id": reserva.evento_id, "cantidad": reserva.cantidad}
    
    # --- PASO 1: Descontar del Inventario ---
    try:
        res_inv = requests.post(f"{INVENTARIO_URL}/inventario/descontar", json=payload, timeout=2.0)
        if res_inv.status_code != 200:
            # Si el inventario dice que no hay stock, paramos de inmediato
            detalles_error = res_inv.json().get("detail", "Error en inventario")
            raise HTTPException(status_code=res_inv.status_code, detail=detalles_error)
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=503, detail="El Servicio de Inventario no responde")

    # --- PASO 2: Procesar el Pago (Pasarela Lenta) ---
    pago_exitoso = False
    try:
        # Se envía la petición de pago
        res_pago = requests.post(f"{PAGOS_URL}/pagar", json={"monto": 25.0 * reserva.cantidad}, timeout=25.0)
        if res_pago.status_code == 200 and res_pago.json().get("status") == "success":
            pago_exitoso = True
    except requests.exceptions.RequestException:
        pago_exitoso = False

    # Si el pago falla (o da timeout), hacemos rollback del inventario inmediatamente
    if not pago_exitoso:
        try:
            requests.post(f"{INVENTARIO_URL}/inventario/devolver", json=payload, timeout=2.0)
        except requests.exceptions.RequestException:
            print("[ALERTA CRÍTICA] Falló la devolución de stock al inventario. Inconsistencia de datos detectada.")
        
        raise HTTPException(status_code=402, detail="Pago declinado o error de conexión con la pasarela de pagos")

    # --- PASO 3: Enviar la Notificación (Asíncrona y no bloqueante para el cliente) ---
    try:
        requests.post(f"{NOTIFICACIONES_URL}/notificar", json={"email": reserva.usuario_email, "mensaje": "¡Tus entradas están listas!"}, timeout=2.0)
    except requests.exceptions.RequestException:
        # Si el servicio de notificaciones falla, NO arruinamos la compra del usuario.
        # Imprimimos el log y dejamos que la reserva sea exitosa (Fallo controlado/tolerante)
        print("[LOG] El correo de confirmación no se pudo enviar, pero el pago ya fue cobrado.")

    return {
        "status": "success",
        "message": "Reserva procesada, pagada y confirmada con éxito."
    }