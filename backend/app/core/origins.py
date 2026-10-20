"""The same exact allowlist applies to CORS and browser WS handshakes."""

from app.core.settings import settings


def websocket_origin_allowed(headers) -> bool:
    origins = headers.getlist("origin")
    return len(origins) == 1 and origins[0] in settings.allowed_origins
