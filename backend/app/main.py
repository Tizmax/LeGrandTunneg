"""Point d'entrée FastAPI pour Le Grand Tunneg.

Pour l'instant : application minimale avec un endpoint de health check.
La logique de jeu, les routes API et les handlers WebSocket seront ajoutés
dans les blocs suivants (voir docs/exec-plans/reconstruction-le-grand-tunneg.md).
"""

from fastapi import FastAPI

app = FastAPI(title="Le Grand Tunneg")


@app.get("/health")
async def health() -> dict[str, str]:
    """Endpoint de health check, utilisé notamment par Railway."""
    return {"status": "ok"}
