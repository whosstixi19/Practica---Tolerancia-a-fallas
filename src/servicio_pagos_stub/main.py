from fastapi import FastAPI
from pydantic import BaseModel
import os
import asyncio

app = FastAPI(title="Stub de Pagos Caótico")

class PagoRequest(BaseModel):
    monto: float

@app.post("/pagar")
async def pagar(pago: PagoRequest):
    latencia_activa = os.getenv("LATENCIA_ACTIVA", "false").lower() == "true"
    
    if latencia_activa:
        print("[CAOS ACTIVADO] Aplicando retraso artificial de 20 segundos.")
        await asyncio.sleep(20.0)
        
    return {"status": "success", "transaccion_id": "tx_k8s_resilient", "monto_procesado": pago.monto}
