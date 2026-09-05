import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.portfolio import get_portfolio_summary

app = FastAPI(title="Portfolio Inversión", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(BASE_DIR, "IN")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

@app.get("/api/portfolio")
def api_get_portfolio(refresh: bool = Query(default=False)):
    try:
        # Si refresh=true, ignora la caché y consulta de nuevo los precios actuales del mercado
        data = get_portfolio_summary(IN_DIR, force_refresh=refresh)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
