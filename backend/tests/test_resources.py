"""Shared configuration, transport, lifecycle and static confinement regressions."""

import asyncio
import socket
from dataclasses import fields
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.core.limits import TokenBucket
from app.core.origins import websocket_origin_allowed
from app.core.settings import Settings, settings, valid_origin
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for item in fields(Settings):
        monkeypatch.delenv(item.name.upper(), raising=False)
    previous = {item.name: getattr(settings, item.name) for item in fields(settings)}
    yield
    for name, value in previous.items():
        setattr(settings, name, value)


def test_defaults_and_environment_loading(monkeypatch):
    config = Settings()
    config.validate()
    assert config.max_players == 16
    assert config.max_message_bytes == config.max_rest_body_bytes == 8192
    assert config.allowed_origins == ("http://localhost:5173", "http://127.0.0.1:5173")
    monkeypatch.setenv("MAX_ROOMS", "7")
    monkeypatch.setenv("AUTH_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://example.com,https://example.com:8443")
    config = Settings()
    config.validate()
    assert config.max_rooms == 7
    assert config.auth_timeout_seconds == 1.5
    assert config.allowed_origins == ("https://example.com", "https://example.com:8443")


NUMERIC_FIELDS = [item for item in fields(Settings) if item.type in {int, float}]


@pytest.mark.parametrize("item", NUMERIC_FIELDS, ids=lambda item: item.name)
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf", "bad", ""])
def test_invalid_numeric_environment(item, value, monkeypatch):
    monkeypatch.setenv(item.name.upper(), value)
    with pytest.raises(ValueError):
        Settings().validate()


@pytest.mark.parametrize("item", NUMERIC_FIELDS, ids=lambda item: item.name)
@pytest.mark.parametrize("value", [False, float("nan"), float("inf"), -1, 0])
def test_invalid_direct_numeric_configuration(item, value):
    config = Settings()
    setattr(config, item.name, value)
    with pytest.raises(ValueError):
        config.validate()


def test_cross_setting_bounds():
    with pytest.raises(ValueError, match="MAX_PLAYERS"):
        Settings(max_players=17).validate()
    with pytest.raises(ValueError, match="CLEANUP"):
        Settings(room_idle_ttl_seconds=5, room_cleanup_interval_seconds=6).validate()
    with pytest.raises(ValueError, match="PORT"):
        Settings(port=65536).validate()
    with pytest.raises(ValueError):
        Settings(max_rooms=1.5).validate()
    Settings(max_players=16, room_idle_ttl_seconds=5, room_cleanup_interval_seconds=5).validate()


@pytest.mark.parametrize("origin", [
    "*", "null", "", "https://example.com/", "https://example.com/path",
    "https://example.com?x=1", "https://example.com#x", "https://example.com?",
    "https://user@example.com", "https://@example.com", "https://example.com:",
    "https://example.com:0", "https://example.com:65536", "https://*.example.com",
    "https://example.com\\evil", "https://example .com", "ftp://example.com",
    "https://[invalid]", "https://a,b", "https://-example.com",
    "https://EXAMPLE.com", "https://example.com:443", "http://example.com:80",
    "https://example.com:08443", "HTTPS://example.com",
    "https://127.1", "https://2130706433", "https://0x7f000001",
    "https://0177.0.0.1", "https://127.0.0.01",
])
def test_invalid_origins(origin):
    assert not valid_origin(origin)
    with pytest.raises(ValueError):
        Settings(allowed_origins=(origin,)).validate()


def test_origin_list_and_production_validation(monkeypatch):
    with pytest.raises(ValueError):
        Settings(allowed_origins=()).validate()
    with pytest.raises(ValueError):
        Settings(allowed_origins=("https://example.com", "https://example.com")).validate()
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="Production"):
        Settings().validate()
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://example.com")
    with pytest.raises(ValueError, match="Production"):
        Settings().validate()
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://example.com")
    Settings().validate()


@pytest.mark.parametrize("hops", [("*",), ("0.0.0.0/0",), ("::/0",), ("arbitrary",)])
def test_untrusted_proxy_configuration(hops):
    with pytest.raises(ValueError, match="TRUSTED_PROXY_HOPS"):
        Settings(trusted_proxy_hops=hops).validate()


def test_token_bucket_fakeclock():
    now = [100.0]
    bucket = TokenBucket(2, 2, clock=lambda: now[0])
    assert bucket.consume() and bucket.consume()
    assert not bucket.consume()
    assert bucket.retry_after() == 1
    now[0] += .49
    assert not bucket.consume()
    now[0] += .01
    assert bucket.consume()
    now[0] += 100
    assert bucket.consume() and bucket.consume()
    assert not bucket.consume()
    now[0] -= 100
    assert not bucket.consume()
    slow = TokenBucket(.1, 1, clock=lambda: now[0])
    assert slow.consume()
    assert slow.retry_after() == 10


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_token_bucket_invalid_parameters(value):
    with pytest.raises(ValueError):
        TokenBucket(value, 1)
    with pytest.raises(ValueError):
        TokenBucket(1, value)


def test_exact_ws_origins():
    settings.allowed_origins = ("https://example.com",)
    assert websocket_origin_allowed(Headers({"origin": "https://example.com"}))
    for value in [None, "null", "https://example.com.evil", "https://example.com/", "http://example.com"]:
        assert not websocket_origin_allowed(Headers({} if value is None else {"origin": value}))
    assert not websocket_origin_allowed(Headers(raw=[
        (b"origin", b"https://example.com"), (b"origin", b"https://example.com")
    ]))


@pytest.fixture
def static_client(tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text("SPA")
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("asset")
    (tmp_path / "secret.txt").write_text("secret")
    (root / "escape.txt").symlink_to(tmp_path / "secret.txt")
    (root / "escaped-dir").symlink_to(tmp_path, target_is_directory=True)
    return TestClient(create_app(Settings(), root)), root


def test_safe_frontend_and_assets(static_client):
    client, _ = static_client
    assert client.get("/").text == "SPA"
    assert client.get("/play/ABCD").text == "SPA"
    assert client.get("/apiary").text == "SPA"
    assert client.get("/assets/app.js").text == "asset"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", [
    "/api", "/api/missing", "/ws", "/ws/missing", "/health/missing",
    "/escape.txt", "/escaped-dir/missing", "/escaped-dir/secret.txt",
    "/%2e%2e/secret.txt", "/assets/%2e%2e/index.html", "/%5csecret.txt",
])
def test_unsafe_static_paths_never_fallback(static_client, path):
    client, _ = static_client
    response = client.get(path)
    assert response.status_code == 404
    assert "secret" not in response.text
    assert response.text != "SPA"


@pytest.mark.parametrize("target", ["index.html", "assets"])
def test_index_and_asset_directory_symlink_confinement(static_client, tmp_path, target):
    client, root = static_client
    destination = root / target
    if target == "assets":
        (destination / "app.js").unlink()
        destination.rmdir()
        destination.symlink_to(tmp_path, target_is_directory=True)
        path = "/assets/secret.txt"
    else:
        destination.unlink()
        destination.symlink_to(tmp_path / "secret.txt")
        path = "/unknown"
    assert client.get(path).status_code == 404


def test_missing_static_directory(tmp_path):
    client = TestClient(create_app(Settings(), tmp_path / "missing"))
    assert client.get("/frontend").status_code == 404


def test_startup_refreshes_environment_and_cors(monkeypatch):
    from app.main import manager

    async def cleanup_loop():
        await asyncio.Event().wait()

    application = create_app()
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://fresh.example")
    monkeypatch.setenv("MAX_ROOMS", "3")
    with patch.object(manager, "cleanup_loop", cleanup_loop, create=True):
        with TestClient(application) as client:
            assert settings.max_rooms == 3
            assert application.state.settings is settings
            response = client.get("/health", headers={"Origin": "https://fresh.example"})
            assert response.headers["access-control-allow-origin"] == "https://fresh.example"
            response = client.get("/health", headers={"Origin": "http://localhost:5173"})
            assert "access-control-allow-origin" not in response.headers
            response = client.options("/health", headers={
                "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"
            })
            assert response.status_code == 400
        assert application.state.cleanup_task.cancelled()


def test_startup_rejects_environment_changed_after_import(monkeypatch):
    application = create_app()
    monkeypatch.setenv("MAX_ROOMS", "0")
    with pytest.raises(ValueError, match="MAX_ROOMS"):
        with TestClient(application):
            pass


def test_injected_configuration_is_shared_with_websocket_checks():
    from app.main import manager

    async def cleanup_loop():
        await asyncio.Event().wait()

    application = create_app(Settings(allowed_origins=("https://custom.example",), max_rooms=3))
    with patch.object(manager, "cleanup_loop", cleanup_loop, create=True):
        with TestClient(application) as client:
            headers = Headers({"origin": "https://custom.example"})
            assert websocket_origin_allowed(headers)
            assert not websocket_origin_allowed(Headers({"origin": "http://localhost:5173"}))
            assert settings.max_rooms == 3
            response = client.get("/health", headers=headers)
            assert response.headers["access-control-allow-origin"] == "https://custom.example"


def test_lifespan_cancels_and_awaits_cleanup():
    from app.main import manager

    async def scenario():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def cleanup_loop():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cancelled.set()

        application = create_app(Settings())
        with patch.object(manager, "cleanup_loop", cleanup_loop, create=True):
            async with application.router.lifespan_context(application):
                await started.wait()
                assert not cancelled.is_set()
            assert cancelled.is_set()
            assert application.state.cleanup_task.cancelled()

    asyncio.run(scenario())


def test_production_transport_configuration(monkeypatch):
    from app.serve import main

    monkeypatch.setenv("MAX_MESSAGE_BYTES", "1024")
    monkeypatch.setenv("PORT", "9001")
    with patch("app.serve.uvicorn.run") as run:
        main()
    args, kwargs = run.call_args
    assert args == ("app.main:app",)
    assert kwargs["ws"] == "websockets"
    assert kwargs["ws_max_size"] == 1024
    assert kwargs["ws_max_queue"] == 4
    assert kwargs["workers"] == 1
    assert kwargs["port"] == 9001
    assert not kwargs["proxy_headers"]
    assert not kwargs["forwarded_allow_ips"]
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "127.0.0.1,10.0.0.0/8")
    with patch("app.serve.uvicorn.run") as run:
        main()
    assert run.call_args.kwargs["proxy_headers"]
    assert run.call_args.kwargs["forwarded_allow_ips"] == ["127.0.0.1", "10.0.0.0/8"]


@pytest.mark.parametrize("frame", ["\u00e9" * 129, b"x" * 257])
def test_live_transport_rejects_oversized_frames_before_app_receives(monkeypatch, frame):
    import uvicorn
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    from app.serve import main

    monkeypatch.setenv("MAX_MESSAGE_BYTES", "256")
    with patch("app.serve.uvicorn.run") as run:
        main()
    options = dict(run.call_args.kwargs)
    options.pop("host")
    options.pop("port")
    received = []
    transport_app = FastAPI()

    @transport_app.websocket("/probe")
    async def probe(websocket: WebSocket):
        await websocket.accept()
        try:
            received.append(await websocket.receive_text())
        except WebSocketDisconnect:
            pass

    async def scenario():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            server = uvicorn.Server(uvicorn.Config(
                transport_app, lifespan="off", log_level="critical", **options
            ))
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(5):
                    while not server.started:
                        if task.done():
                            await task
                            pytest.fail("Transport exited before startup")
                        await asyncio.sleep(.01)
                    port = listener.getsockname()[1]
                    async with connect(f"ws://127.0.0.1:{port}/probe") as websocket:
                        await websocket.send(frame)
                        with pytest.raises(ConnectionClosed) as closed:
                            await websocket.recv()
                        assert closed.value.rcvd.code == 1009
                    assert received == []
            finally:
                server.should_exit = True
                await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())
