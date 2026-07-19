from fastapi import FastAPI
from pydantic import BaseModel
import random
import os

app = FastAPI(title="Stub de Notificaciones Caótico")

class NotificacionRequest(BaseModel):
    email: str
    mensaje: str

@app.post("/notificar")
async def notificar(notif: NotificacionRequest):
    falla_activa = os.getenv("FALLA_INTERMITENTE", "true").lower() == "true"
    
    if falla_activa and random.random() < 0.5:
        print(f"[CAOS NOTIFICACIONES] Fallo simulado para {notif.email}")
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Servicio de correos temporalmente caído.")
    
    print(f"[NOTIFICACIONES] Enviando correo a {notif.email}: {notif.mensaje}")
    return {"status": "success", "mensaje": f"Notificación enviada con éxito a {notif.email}"}
