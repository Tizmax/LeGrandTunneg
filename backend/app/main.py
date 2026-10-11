"""Point d'entrée FastAPI pour Le Grand Tunneg.

Mode room multi en mémoire (Bloc 3/4/5, sans persistance Postgres pour
l'instant — voir docs/websocket-protocol.md, section "Limitations connues").
Le packaging Railway (service unique servant aussi le build frontend statique)
sera ajouté au Bloc 9.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.rooms import router as rooms_router
from app.api.ws import router as ws_router

app = FastAPI(title="Le Grand Tunneg")

# CORS ouvert en développement : le frontend Vite (http://localhost:5173) et
# le backend (http://127.0.0.1:8000) tournent sur deux ports distincts tant
# que le Bloc 9 (service unique) n'est pas en place.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rooms_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Endpoint de health check, utilisé notamment par Railway."""
    return {"status": "ok"}
