from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import os

app = FastAPI(title="Servicio de Inventario")

# Obtenemos la dirección de Redis desde variables de entorno (útil para K8s)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Conexión a Redis
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

class InventarioRequest(BaseModel):
    evento_id: str
    cantidad: int

# Inicializar un evento de prueba con 100 asientos al arrancar el servicio
@app.on_event("startup")
async def startup_event():
    try:
        if not r.exists("evento_1"):
            r.set("evento_1", 100)
            print("[INVENTARIO] Evento 'evento_1' inicializado con 100 entradas.")
    except redis.ConnectionError:
        print("[ALERTA] No se pudo conectar a Redis. Asegúrate de tenerlo corriendo.")

@app.post("/inventario/descontar")
async def descontar_inventario(data: InventarioRequest):
    try:
        stock_actual = r.get(data.evento_id)
        if stock_actual is None:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
        
        stock_actual = int(stock_actual)
        if stock_actual < data.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente para la compra")
        
        # Reducción atómica segura para evitar condiciones de carrera teóricas
        nuevo_stock = r.decrby(data.evento_id, data.cantidad)
        return {
            "status": "success",
            "evento_id": data.evento_id,
            "stock_restante": nuevo_stock
        }
    except redis.ConnectionError:
        raise HTTPException(status_code=500, detail="Error de conexión con la base de datos de inventario")

@app.post("/inventario/devolver")
async def devolver_inventario(data: InventarioRequest):
    try:
        nuevo_stock = r.incrby(data.evento_id, data.cantidad)
        return {
            "status": "success",
            "evento_id": data.evento_id,
            "stock_restante": nuevo_stock
        }
    except redis.ConnectionError:
        raise HTTPException(status_code=500, detail="Error de conexión con la base de datos de inventario")