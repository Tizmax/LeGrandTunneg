"""Real HTTP/WS transport with an injected double, not a Postgres/Railway proof."""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus


ORIGIN = "https://tunneg.example.test"


@pytest.fixture
def live_service():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = {
        **os.environ,
        "PORT": str(port),
        "APP_ENV": "production",
        "ALLOWED_ORIGINS": ORIGIN,
        "REST_RATE_PER_SECOND": "1000",
        "REST_RATE_BURST": "1000",
        "WS_COMMAND_RATE_PER_SECOND": "1000",
        "WS_COMMAND_RATE_BURST": "1000",
        "WS_GLOBAL_RATE_PER_SECOND": "1000",
        "WS_GLOBAL_RATE_BURST": "1000",
    }
    process = subprocess.Popen(
        [os.sys.executable, "-m", "uvicorn", "tests.persistence_double:transport_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--ws-max-size", "8192"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with urllib.request.urlopen(base + "/health", timeout=0.2) as response:
                    assert json.load(response) == {"status": "ok"}
                break
            except (OSError, urllib.error.URLError):
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("Local production entrypoint failed to start")
                time.sleep(0.03)
        yield base, f"ws://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def post(base, path, body):
    request = urllib.request.Request(
        base + path, json.dumps(body).encode(),
        {"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        assert response.headers["Cache-Control"] == "no-store"
        return json.load(response)


async def receive(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), 3))


async def authenticate(url, identity):
    ws = await connect(url, origin=ORIGIN)
    await ws.send(json.dumps({"type": "session:auth", "payload": {
        "localPlayerId": identity["localPlayerId"],
        "sessionToken": identity["sessionToken"],
    }}))
    message = await receive(ws)
    assert message["type"] == "room:state_sync"
    assert identity["sessionToken"] not in json.dumps(message)
    return ws, message["payload"]["state"]


@pytest.mark.asyncio
async def test_real_transport_complete_game_replacement_revoke_and_size(live_service):
    base, ws_base = live_service
    host = post(base, "/api/rooms", {"pseudo": "Paul"})
    code = host["code"]
    alice, bob = [post(base, f"/api/rooms/{code}/join", {"pseudo": name})
                  for name in ("Alice", "Bob")]
    url = f"{ws_base}/ws/{code}"
    sockets = {}
    try:
        for identity in (host, alice, bob):
            ws, _ = await authenticate(url, identity)
            sockets[identity["localPlayerId"]] = ws
        presenter = sockets[host["localPlayerId"]]
        await presenter.send(json.dumps({"type": "theme:add", "payload": {"label": "Cinema"}}))
        # Presence commits from earlier authentications may precede this barrier.
        for ws in sockets.values():
            while True:
                state = (await receive(ws))["payload"]["state"]
                if state["themes"]:
                    break

        async def action(ws, command, payload=None):
            await ws.send(json.dumps({"type": command, "payload": payload or {}}))
            states = []
            for peer in sockets.values():
                message = await receive(peer)
                assert message["type"] == "room:state_sync", message
                states.append(message["payload"]["state"])
            assert all(state == states[0] for state in states)
            return states[0]

        # Invalid JSON is recoverable on this very same TCP/WS connection.
        await presenter.send("null")
        assert (await receive(presenter))["payload"] == {
            "code": "invalid_payload", "message": "Invalid message.",
        }
        await presenter.send("[" * 1500 + "]" * 1500)
        assert (await receive(presenter))["payload"]["code"] == "invalid_payload"
        state = await action(presenter, "game:start")
        first = state["players"][state["currentPlayerIndex"]]["id"]
        second = next(p["localPlayerId"] for p in (alice, bob) if p["localPlayerId"] != first)
        await action(presenter, "choice:reveal")
        await action(sockets[first], "theme:select", {"index": 0})
        await action(presenter, "timer:start")
        await action(presenter, "answer:good")
        await action(presenter, "choice:reveal")
        state = await action(sockets[first], "answer:vault")
        assert state["themes"][0]["completed"] is False
        await action(presenter, "choice:reveal")
        await action(sockets[second], "theme:select", {"index": 0})
        for square in range(2, 11):
            await action(presenter, "timer:start")
            state = await action(presenter, "answer:good")
            if square < 10:
                await action(presenter, "choice:reveal")
                await action(sockets[second], "answer:continue")
        assert state["phase"] == "end"
        assert state["turnStatus"] == "idle"
        assert state["currentPlayerIndex"] is state["rotationAnchorIndex"] is None
        assert {p["id"]: p["points"] for p in state["players"]} == {
            host["localPlayerId"]: 0, first: 1, second: 22,
        }
        state = await action(presenter, "game:end_early")
        old_alice = sockets[alice["localPlayerId"]]
        replacement, _ = await authenticate(url, alice)
        terminal = await receive(old_alice)
        assert terminal["payload"]["code"] == "session_replaced"
        with pytest.raises(ConnectionClosed) as closed:
            await old_alice.recv()
        assert closed.value.rcvd.code == 4409
        sockets[alice["localPlayerId"]] = replacement
        # Transfer is effective on the pre-existing authenticated sockets.
        await presenter.send(json.dumps({"type": "presenter:transfer", "payload": {
            "targetPlayerId": alice["localPlayerId"],
        }}))
        for ws in sockets.values():
            while True:
                message = await receive(ws)
                state = message["payload"]["state"]
                if next(p for p in state["players"] if p["id"] == alice["localPlayerId"])["isPresenter"]:
                    break
        await presenter.send(json.dumps({"type": "theme:add", "payload": {"label": "Forbidden"}}))
        assert (await receive(presenter))["payload"]["code"] == "forbidden_role"
        bob_index = next(i for i, p in enumerate(state["players"]) if p["id"] == bob["localPlayerId"])
        await replacement.send(json.dumps({"type": "player:remove", "payload": {"index": bob_index}}))
        bob_ws = sockets.pop(bob["localPlayerId"])
        assert (await receive(bob_ws))["type"] == "player:kicked"
        assert (await receive(bob_ws))["payload"]["code"] == "player_kicked"
        with pytest.raises(ConnectionClosed) as closed:
            await bob_ws.recv()
        assert closed.value.rcvd.code == 4403
        with pytest.raises(urllib.error.HTTPError) as rejected:
            post(base, f"/api/rooms/{code}/join", {
                "localPlayerId": bob["localPlayerId"], "sessionToken": bob["sessionToken"],
            })
        assert rejected.value.code == 401
        # Drain removal state then prove the production WS transport limit.
        for ws in sockets.values():
            assert (await receive(ws))["type"] == "room:state_sync"
        await replacement.send(" " * 8193)
        with pytest.raises(ConnectionClosed) as closed:
            await replacement.recv()
        assert closed.value.rcvd.code == 1009
    finally:
        for ws in sockets.values():
            await ws.close()


@pytest.mark.asyncio
async def test_real_transport_origin_before_upgrade(live_service):
    _, ws_base = live_service
    with pytest.raises(InvalidStatus) as rejected:
        async with connect(ws_base + "/ws/ZZZZ", origin="https://evil.example.test"):
            pytest.fail("Origin must be rejected before WS acceptance")
    assert rejected.value.response.status_code == 403
