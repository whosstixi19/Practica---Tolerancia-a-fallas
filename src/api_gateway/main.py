from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from contextlib import asynccontextmanager
from limits import parse
from limits.strategies import MovingWindowRateLimiter
from limits.storage import MemoryStorage

http_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient()
    yield
    await http_client.aclose()

app = FastAPI(title="API Gateway - Capa Resiliencia", lifespan=lifespan)

storage = MemoryStorage()
limiter = MovingWindowRateLimiter(storage)
limite_peticiones = parse("5/second")

RESERVAS_URL = "http://servicio-reservas:8001"

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    cliente_ip = request.client.host
    if not limiter.hit(limite_peticiones, cliente_ip):
        return JSONResponse(
            status_code=429,
            content={"status": "error", "message": "Saturación: Demasiadas peticiones."}
        )
    return await call_next(request)

@app.post("/api/v1/comprar")
async def proxy_comprar(payload: dict):
    try:
        response = await http_client.post(f"{RESERVAS_URL}/reservas", json=payload, timeout=30.0)
        return response.json()
    except httpx.RequestError:
        return JSONResponse(status_code=503, content={"detail": "Servicio de reservas offline."})
