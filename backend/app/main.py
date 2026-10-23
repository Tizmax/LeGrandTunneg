"""Single-process API/WS service with confined frontend SPA delivery."""

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import fields
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.rooms import router as rooms_router
from app.api.ws import router as ws_router
from app.api import rooms, ws
from app.core.limits import TokenBucket
from app.core.settings import Settings, settings
from app.rooms.manager import room_manager as manager
from app.persistence.config import DatabaseConfig
from app.persistence.store import PostgresStore

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(config: Settings | None = None, static_dir: Path | None = None, *, store=None) -> FastAPI:
    configuration = settings if config is None else config
    root = (_STATIC_DIR if static_dir is None else static_dir).resolve()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        fresh = Settings() if config is None else config
        fresh.validate()
        # API/manager modules share this object's identity, including injected config.
        for item in fields(fresh):
            setattr(settings, item.name, getattr(fresh, item.name))
        rooms.rest_bucket = TokenBucket(settings.rest_rate_per_second, settings.rest_rate_burst)
        ws.upgrade_bucket = TokenBucket(settings.ws_upgrade_rate_per_second, settings.ws_upgrade_rate_burst)
        ws.global_bucket = TokenBucket(settings.ws_global_rate_per_second, settings.ws_global_rate_burst)
        manager.store = store if store is not None else PostgresStore(DatabaseConfig.from_environment())
        cleanup = None
        try:
            await manager.start()
            cleanup = asyncio.create_task(manager.cleanup_loop(), name="room-idle-cleanup")
            application.state.cleanup_task = cleanup
            yield
        finally:
            manager.started = False
            if cleanup is not None:
                cleanup.cancel()
                with suppress(asyncio.CancelledError):
                    await cleanup
            await manager.store.close()

    application = FastAPI(title="Le Grand Tunneg", lifespan=lifespan)
    application.state.settings = configuration

    class ExactCORSMiddleware(CORSMiddleware):
        def is_allowed_origin(self, origin: str) -> bool:
            return origin in configuration.allowed_origins

    application.add_middleware(
        ExactCORSMiddleware,
        allow_origins=(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(rooms_router)
    application.include_router(ws_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready")
    async def ready() -> JSONResponse:
        if not await manager.ready():
            raise HTTPException(status_code=503, detail={
                "code": "persistence_unavailable", "message": "Room persistence unavailable.",
            }, headers={"Cache-Control": "no-store"})
        return JSONResponse({"status": "ready"}, headers={"Cache-Control": "no-store"})

    @application.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.split("/", 1)[0] in {"api", "ws", "health"}:
            raise HTTPException(status_code=404)
        # Reject traversal itself, even if it would normalize back inside root.
        if ".." in full_path.split("/") or "\\" in full_path or "\x00" in full_path:
            raise HTTPException(status_code=404)
        try:
            candidate = (root / full_path).resolve()
            if not candidate.is_relative_to(root):
                raise HTTPException(status_code=404)
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            # Missing asset files are not frontend routes.
            if full_path.split("/", 1)[0] == "assets":
                raise HTTPException(status_code=404)
            index = (root / "index.html").resolve()
            if not index.is_relative_to(root) or not index.is_file():
                raise HTTPException(status_code=404)
            return FileResponse(index)
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(status_code=404) from None

    return application


app = create_app()
