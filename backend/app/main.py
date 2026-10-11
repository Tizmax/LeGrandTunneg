"""Point d'entrée FastAPI pour Le Grand Tunneg.

Mode room multi en mémoire (Bloc 3/4/5, sans persistance Postgres pour
l'instant — voir docs/websocket-protocol.md, section "Limitations connues").

Bloc 9 (packaging Railway, service unique) : ce process sert à la fois
l'API/WS et le bundle frontend statique (frontend/dist, copié dans
app/static par le Dockerfile de build). Aucune valeur sensible ni host/port
n'est codée en dur : tout vient de l'environnement.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.rooms import router as rooms_router
from app.api.ws import router as ws_router

app = FastAPI(title="Le Grand Tunneg")

# CORS : en développement les deux ports Vite/uvicorn sont distincts donc on
# ouvre tout ("*"). En production (service unique, Bloc 9) le frontend est
# servi par ce même process donc l'origine est toujours la même — on peut
# restreindre via la variable ALLOWED_ORIGINS (liste séparée par des virgules)
# si un jour le frontend est servi ailleurs (ex. preview déployée séparément).
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
_allowed_origins = (
    ["*"]
    if _allowed_origins_env.strip() == "*"
    else [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rooms_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Endpoint de health check, utilisé notamment par Railway."""
    return {"status": "ok"}


# --- Service du frontend statique (Bloc 9) ---------------------------------
# frontend/dist est copié dans app/static par le Dockerfile de build (voir
# Dockerfile à la racine). En développement ce dossier n'existe pas : les
# routes ci-dessous sont alors simplement absentes (le frontend tourne via
# `npm run dev` sur son propre port), ce qui ne casse rien.
_STATIC_DIR = Path(__file__).resolve().parent / "static"

if _STATIC_DIR.is_dir():
    _ASSETS_DIR = _STATIC_DIR / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        """Sert index.html pour toute route non-API (fallback SPA).

        Les routes /api/*, /ws/* et /health sont déjà capturées par les
        routers inclus ci-dessus et ne passent jamais par ce handler
        (FastAPI résout les routes déclarées avant ce catch-all générique).
        """
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
