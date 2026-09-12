import os
import time
import threading
import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.portfolio import (
    get_portfolio_summary,
    insert_operacion,
    compra_existe_alta,
    KNOWN_FUNDS,
)
from app.update_navs import update_all_navs

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(BASE_DIR, "IN")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

HORA_ACTUALIZACION = 18  # hora local a la que se actualizan los NAVs cada día

_update_lock = threading.Lock()


def _run_update():
    """Ejecuta la actualización de NAVs protegiendo contra llamadas simultáneas."""
    if not _update_lock.acquire(blocking=False):
        return
    try:
        update_all_navs(IN_DIR)
    except Exception as e:
        print(f"Error en la actualización de NAVs: {e}")
    finally:
        _update_lock.release()


def _scheduler_loop():
    """Hilo daemon: ejecuta la actualización cada día a la hora indicada."""
    while True:
        now = datetime.datetime.now()
        target = now.replace(hour=HORA_ACTUALIZACION, minute=0, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)
        seconds_to_wait = (target - now).total_seconds()
        time.sleep(seconds_to_wait)
        _run_update()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar: actualiza en segundo plano sin bloquear la web.
    threading.Thread(target=_run_update, daemon=True).start()
    # Programador diario a las 18:00.
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    yield


app = FastAPI(title="Portfolio Inversión", version="1.2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OperacionCreate(BaseModel):
    isin: str
    fecha: str  # YYYY-MM-DD
    importe: float
    participaciones: float
    precio_titulo: float | None = None
    operador: str | None = None


@app.get("/api/portfolio")
def api_get_portfolio():
    # Solo lectura: los NAVs se actualizan en el flujo de escritura (update_navs).
    try:
        return get_portfolio_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/operaciones")
def api_create_operacion(op: OperacionCreate):
    # Validación anti-duplicados: la compra ya debe estar registrada.
    if compra_existe_alta(op.isin, op.fecha, op.importe, op.participaciones):
        raise HTTPException(
            status_code=409,
            detail=f"La compra del {op.fecha} ({op.isin}) ya está registrada en la BBDD."
        )
    try:
        new_id = insert_operacion(
            isin=op.isin,
            fecha=op.fecha,
            importe=op.importe,
            participaciones=op.participaciones,
            precio_titulo=op.precio_titulo or 0,
            operador=op.operador or KNOWN_FUNDS.get(op.isin, {}).get('operador', '').lower(),
            fuente='manual',
            tipo='Compra',
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not new_id:
        raise HTTPException(
            status_code=409,
            detail=f"La compra del {op.fecha} ({op.isin}) ya está registrada en la BBDD."
        )

    return {
        'id': new_id,
        'isin': op.isin,
        'fecha': op.fecha,
        'importe': op.importe,
        'participaciones': op.participaciones,
        'precio_titulo': op.precio_titulo or round(op.importe / op.participaciones, 4),
        'tipo': 'Compra',
        'operador': op.operador or KNOWN_FUNDS.get(op.isin, {}).get('operador', ''),
        'fuente': 'manual',
    }


@app.get("/")
def read_root():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Frontend no encontrado en frontend/index.html"}


if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)