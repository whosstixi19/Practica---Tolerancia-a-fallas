from fastapi import FastAPI
from pydantic import BaseModel
import asyncio

app = FastAPI(title="Stub de Pagos (Caótico)")

class PagoRequest(BaseModel):
    monto: float

@app.post("/pagar")
async def pagar(pago: PagoRequest):
    # CAOS: Simulamos latencia extrema en la red externa
    print("[STUB-PAGOS] Procesando transacción lenta de pago...")
    await asyncio.sleep(20.0) # Esto forzará los timeouts del llamador
    
    return {
        "status": "success",
        "transaccion_id": "tx_fake_uuid_12345",
        "monto_procesado": pago.monto
    }