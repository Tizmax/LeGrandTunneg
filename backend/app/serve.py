"""Production entrypoint: resource limits must reach the WS transport layer."""

import uvicorn

from app.core.settings import Settings


def main() -> None:
    settings = Settings()
    settings.validate()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        workers=1,
        ws="websockets",
        ws_max_size=settings.max_message_bytes,
        ws_max_queue=4,
        ws_per_message_deflate=False,
        proxy_headers=bool(settings.trusted_proxy_hops),
        forwarded_allow_ips=list(settings.trusted_proxy_hops),
    )


if __name__ == "__main__":
    main()
