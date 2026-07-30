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

SCRIPT_DESCONTAR_ATOMICO = """
local stock_actual = redis.call('GET', KEYS[1])
if not stock_actual then
    return {-1, -1}
end

stock_actual = tonumber(stock_actual)
local cantidad = tonumber(ARGV[1])

if stock_actual < cantidad then
    return {0, stock_actual}
end

local nuevo_stock = redis.call('DECRBY', KEYS[1], cantidad)
return {1, nuevo_stock}
"""

# Inicializar un evento de prueba con 100 asientos al arrancar el servicio
@app.on_event("startup")
async def startup_event():
    try:
        if not r.exists("evento_1"):
            r.set("evento_1", 100)
            print("[INVENTARIO] Evento 'evento_1' inicializado con 100 entradas.")
    except Exception:
        print("[ALERTA] No se pudo conectar a Redis. Asegúrate de tenerlo corriendo.")

@app.post("/inventario/descontar")
async def descontar_inventario(data: InventarioRequest):
    try:
        if data.cantidad <= 0:
            raise HTTPException(status_code=400, detail="La cantidad debe ser mayor que cero")

        # Codigo anterior:
        # stock_actual = r.get(data.evento_id)
        # if stock_actual is None:
        #     raise HTTPException(status_code=404, detail="Evento no encontrado")
        #
        # stock_actual = int(stock_actual)
        # if stock_actual < data.cantidad:
        #     raise HTTPException(status_code=400, detail="Stock insuficiente para la compra")
        #
        # nuevo_stock = r.decrby(data.evento_id, data.cantidad)
        #
        # Por que se cambio:
        # GET -> validar -> DECRBY no es atomico como secuencia completa. Con dos compras
        # simultaneas del ultimo asiento, ambas podian pasar la validacion antes del DECRBY.
        # El script Lua se ejecuta completo dentro de Redis y evita stock negativo.
        resultado = r.eval(SCRIPT_DESCONTAR_ATOMICO, 1, data.evento_id, data.cantidad)
        codigo = int(resultado[0])
        nuevo_stock = int(resultado[1])

        if codigo == -1:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
        
        if codigo == 0:
            raise HTTPException(status_code=400, detail="Stock insuficiente para la compra")
        
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
