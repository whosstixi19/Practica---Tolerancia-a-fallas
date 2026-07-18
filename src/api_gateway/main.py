from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os

app = FastAPI(title="API Gateway")

RESERVAS_URL = os.getenv("RESERVAS_URL", "http://localhost:8001")

class CompraTicket(BaseModel):
    evento_id: str
    cantidad: int
    usuario_email: str

@app.post("/api/v1/comprar")
async def procesar_compra(compra: CompraTicket):
    # Aquí es donde el Integrante 3 (Tú antes, o tu compañero ahora) inyectará el Rate Limiter
    try:
        response = requests.post(
            f"{RESERVAS_URL}/reservas",
            json={
                "evento_id": compra.evento_id,
                "cantidad": compra.cantidad,
                "usuario_email": compra.usuario_email
            },
            timeout=30.0 # Permitimos tiempo suficiente para que corra el flujo por defecto
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.json().get("detail"))
            
        return response.json()
        
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=503, detail="El sistema de reservas central no se encuentra disponible.")