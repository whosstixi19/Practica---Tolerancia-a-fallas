from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Stub de Notificaciones")

class NotificacionRequest(BaseModel):
    email: str
    mensaje: str

@app.post("/notificar")
async def notificar(notif: NotificacionRequest):
    print(f"[NOTIFICACIONES] Enviando correo electrónico a {notif.email}: {notif.mensaje}")
    return {
        "status": "success",
        "mensaje": f"Notificación enviada con éxito a {notif.email}"
    }