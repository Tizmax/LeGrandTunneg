"""Real REST/WS regressions for the Bloc 13 private-session contract."""

import base64
import hashlib
import json
import re
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import fields

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.api import rooms, ws as ws_api
from app.core.limits import TokenBucket
from app.core.settings import Settings, settings
from app.main import create_app
from app.rooms.manager import room_manager


ORIGIN = "http://localhost:5173"
HEADERS = {"Origin": ORIGIN}
TOKEN = "A" * 43
PID = "ecaa8b4a-762f-4dc2-8b3c-f270f512a45f"


@pytest.fixture
def client(monkeypatch):
    # Lifespan copies config into the shared object; restore all fields later.
    for field in fields(settings):
        monkeypatch.setattr(settings, field.name, getattr(settings, field.name))
    monkeypatch.setattr(room_manager, "_rooms", {})
    monkeypatch.setattr(room_manager, "authenticated_connections", set())
    monkeypatch.setattr(room_manager, "preauth_connections", 0)
    for module, attribute in ((rooms, "rest_bucket"), (ws_api, "upgrade_bucket"),
                              (ws_api, "global_bucket")):
        monkeypatch.setattr(module, attribute, TokenBucket(10000, 10000))
    config = Settings(allowed_origins=(ORIGIN,), ws_command_rate_per_second=10000,
                      ws_command_rate_burst=10000, rest_rate_per_second=10000,
                      rest_rate_burst=10000, ws_upgrade_rate_per_second=10000,
                      ws_upgrade_rate_burst=10000, ws_global_rate_per_second=10000,
                      ws_global_rate_burst=10000)
    with TestClient(create_app(config)) as test_client:
        yield test_client


def post(client, path, payload):
    return client.post(path, json=payload, headers=HEADERS)


def create(client, name="Host"):
    response = post(client, "/api/rooms", {"pseudo": name})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"code", "localPlayerId", "role", "sessionToken"}
    return response.json()


def join(client, host, name="Alice", role="joueur"):
    response = post(client, f"/api/rooms/{host['code']}/join", {"pseudo": name, "role": role})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"code", "localPlayerId", "role", "sessionToken", "state"}
    return response.json()


def proof(identity):
    return {key: identity[key] for key in ("localPlayerId", "sessionToken")}


def resume(client, identity):
    return post(client, f"/api/rooms/{identity['code']}/join", proof(identity))


def receive(socket):
    # Bound TestClient's otherwise unbounded blocking receive, on its own portal.
    async def bounded():
        with anyio.fail_after(2):
            return await socket._send_rx.receive()

    frame = socket.portal.call(bounded)
    if frame["type"] == "websocket.close":
        raise WebSocketDisconnect(frame.get("code", 1000), frame.get("reason", ""))
    assert frame["type"] == "websocket.send", frame
    return json.loads(frame["text"])


def silent(socket):
    async def probe():
        with anyio.move_on_after(.03):
            return await socket._send_rx.receive()

    assert socket.portal.call(probe) is None


def command(socket, event, payload=None):
    socket.send_json({"type": event, "payload": {} if payload is None else payload})


def sync(socket, identity=None):
    message = receive(socket)
    assert message["type"] == "room:state_sync", message
    assert set(message["payload"]) == {"code", "role", "localPlayerId", "state"}
    if identity:
        for key in ("code", "localPlayerId", "role"):
            assert message["payload"][key] == identity[key]
    return message["payload"]["state"]


@contextmanager
def connected(client, identity):
    with client.websocket_connect(f"/ws/{identity['code']}", headers=HEADERS) as socket:
        command(socket, "session:auth", proof(identity))
        yield socket, sync(socket, identity)


@contextmanager
def participants(client, *identities):
    sockets = []
    with ExitStack() as stack:
        for identity in identities:
            socket, state = stack.enter_context(connected(client, identity))
            for observer in sockets:
                assert sync(observer) == state
            sockets.append(socket)
        yield sockets, state


def error(socket, code="invalid_payload"):
    message = receive(socket)
    assert message["type"] == "error", message
    assert set(message["payload"]) == {"code", "message"}
    assert message["payload"]["code"] == code
    if code == "invalid_payload":
        assert message["payload"]["message"] == "Invalid message."


def http_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"detail"}
    assert set(response.json()["detail"]) == {"code", "message"}
    assert response.json()["detail"]["code"] == code


def closed(socket, code, reason=None):
    with pytest.raises(WebSocketDisconnect) as exc:
        receive(socket)
    assert exc.value.code == code
    if reason is not None:
        assert exc.value.reason == reason


def terminal(socket, code, close_code, message, alias=None):
    if alias:
        assert receive(socket) == {"type": alias, "payload": {}}
    assert receive(socket) == {"type": "session:ended", "payload": {"code": code, "message": message}}
    closed(socket, close_code, code)


@pytest.mark.parametrize("payload", [
    None, [], "Host", 1, True, {}, {"pseudo": None}, {"pseudo": False},
    {"pseudo": 123}, {"pseudo": []}, {"pseudo": {}}, {"pseudo": " \t\n"},
    {"pseudo": "x" * 25}, {"pseudo": "Host", "role": "presentateur"},
    {"pseudo": "Host", "sessionToken": TOKEN},
])
def test_create_strict_payload_without_partial_room(client, payload):
    http_error(post(client, "/api/rooms", payload), 422, "invalid_payload")
    assert room_manager._rooms == {}


@pytest.mark.parametrize("raw", [b"", b"{", b"null", b"\xff"])
def test_rest_invalid_json(client, raw):
    http_error(client.post("/api/rooms", content=raw, headers=HEADERS), 422, "invalid_payload")
    assert not room_manager._rooms


@pytest.fixture
def nested_json():
    # Exercise extreme nesting below the byte cap. Decoder recursion limits vary
    # by Python version; rejection must be safe whether decoding succeeds or not.
    raw = "[" * 4000 + "0" + "]" * 4000
    assert len(raw.encode("utf-8")) < 8192
    return raw


@pytest.mark.parametrize("endpoint", ["create", "join"])
@pytest.mark.parametrize("escape", [r"\ud800", r"\udfff"])
def test_rest_escaped_lone_surrogate_rejected_without_mutation(client, endpoint, escape):
    host = create(client)
    with connected(client, host) as (observer, state):
        room = room_manager.get_room(host["code"])
        before = (dict(room_manager._rooms), dict(room.proofs), dict(room.roles), dict(room.names))
        path = "/api/rooms" if endpoint == "create" else f"/api/rooms/{host['code']}/join"
        raw = ('{"pseudo":"Name' + escape + '"}').encode("ascii")
        response = client.post(path, content=raw, headers={**HEADERS, "Content-Type": "application/json"})
        http_error(response, 422, "invalid_payload")
        assert (room_manager._rooms, room.proofs, room.roles, room.names) == before
        assert resume(client, host).json()["state"] == state
        silent(observer)


@pytest.mark.parametrize("endpoint", ["create", "join"])
def test_rest_deeply_nested_json_rejected_without_mutation(client, nested_json, endpoint):
    host = create(client)
    with connected(client, host) as (observer, state):
        room = room_manager.get_room(host["code"])
        before = (dict(room_manager._rooms), dict(room.proofs), dict(room.roles), dict(room.names))
        path = "/api/rooms" if endpoint == "create" else f"/api/rooms/{host['code']}/join"
        raw = '{"pseudo":' + nested_json + '}'
        assert len(raw.encode("utf-8")) < 8192
        response = client.post(path, content=raw, headers={**HEADERS, "Content-Type": "application/json"})
        http_error(response, 422, "invalid_payload")
        assert (room_manager._rooms, room.proofs, room.roles, room.names) == before
        assert resume(client, host).json()["state"] == state
        silent(observer)


@pytest.mark.parametrize("event,key", [("player:rename", "name"), ("theme:add", "label")])
@pytest.mark.parametrize("escape", [r"\ud800", r"\udfff"])
def test_ws_escaped_lone_surrogate_rejected_and_same_socket_usable(client, event, key, escape):
    host = create(client)
    screen = join(client, host, "Observer", "ecran-principal")
    with participants(client, host, screen) as (sockets, state):
        actor, observer = sockets
        room = room_manager.get_room(host["code"])
        before = (dict(room.proofs), dict(room.roles), dict(room.names), dict(room.connections))
        actor.send_text('{"type":"' + event + '","payload":{"' + key + '":"Name' + escape + '"}}')
        error(actor)
        assert (room.proofs, room.roles, room.names, room.connections) == before
        assert resume(client, host).json()["state"] == state
        silent(actor)
        silent(observer)
        command(actor, event, {key: "Valid"})
        updated = sync(actor)
        assert sync(observer) == updated
        if event == "player:rename":
            assert updated["players"][0]["name"] == "Valid"
        else:
            assert updated["themes"][0]["label"] == "Valid"


def test_ws_deeply_nested_auth_rejected_without_attachment(client, nested_json):
    host = create(client)
    room = room_manager.get_room(host["code"])
    before = (room.state, dict(room.proofs), dict(room.roles), dict(room.names), room.idle_since)
    raw = '{"type":"session:auth","payload":{"localPlayerId":' + nested_json + ',"sessionToken":"' + TOKEN + '"}}'
    assert len(raw.encode("utf-8")) < 8192
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as socket:
        silent(socket)
        socket.send_text(raw)
        closed(socket, 1008, "invalid_payload")
    assert (room.state, room.proofs, room.roles, room.names, room.idle_since) == before
    assert not room.connections
    assert not room_manager.authenticated_connections
    assert room_manager.preauth_connections == 0
    with connected(client, host):
        pass


def test_ws_deeply_nested_command_rejected_and_same_socket_usable(client, nested_json):
    host = create(client)
    screen = join(client, host, "Observer", "ecran-principal")
    with participants(client, host, screen) as (sockets, state):
        actor, observer = sockets
        room = room_manager.get_room(host["code"])
        before = (dict(room.proofs), dict(room.roles), dict(room.names), dict(room.connections))
        raw = '{"type":"theme:add","payload":{"label":' + nested_json + '}}'
        assert len(raw.encode("utf-8")) < 8192
        actor.send_text(raw)
        error(actor)
        assert (room.proofs, room.roles, room.names, room.connections) == before
        assert resume(client, host).json()["state"] == state
        silent(actor)
        silent(observer)
        command(actor, "theme:add", {"label": "Valid after nesting"})
        updated = sync(actor)
        assert sync(observer) == updated
        assert updated["themes"][0]["label"] == "Valid after nesting"


@pytest.mark.parametrize("payload", [
    {}, None, [], {"pseudo": 2}, {"pseudo": " "}, {"pseudo": "x" * 25},
    {"pseudo": "Alice", "role": "presentateur"}, {"pseudo": "Alice", "role": True},
    {"pseudo": "Alice", "role": []}, {"pseudo": "Alice", "role": None},
    {"pseudo": "Alice", "extra": 1}, {"localPlayerId": PID}, {"sessionToken": TOKEN},
    {"pseudo": "Alice", "localPlayerId": PID, "sessionToken": TOKEN},
    {"localPlayerId": PID, "sessionToken": TOKEN, "role": "joueur"},
    {"localPlayerId": PID.upper(), "sessionToken": TOKEN},
    {"localPlayerId": PID.replace("-", ""), "sessionToken": TOKEN},
    {"localPlayerId": "not-a-uuid", "sessionToken": TOKEN},
    {"localPlayerId": 1, "sessionToken": TOKEN},
    {"localPlayerId": PID, "sessionToken": None},
    {"localPlayerId": PID, "sessionToken": "A" * 42},
    {"localPlayerId": PID, "sessionToken": "A" * 44},
    {"localPlayerId": PID, "sessionToken": "A" * 42 + "B"},
    {"localPlayerId": PID, "sessionToken": "!" * 43},
])
def test_join_strict_payload_never_creates_membership(client, payload):
    host = create(client)
    room = room_manager.get_room(host["code"])
    before = (room.state, dict(room.proofs), dict(room.roles), dict(room.names))
    http_error(post(client, f"/api/rooms/{host['code']}/join", payload), 422, "invalid_payload")
    assert (room.state, room.proofs, room.roles, room.names) == before


def test_tokens_are_independent_digest_only_and_never_public(client, caplog):
    host = create(client, "  Host  ")
    alice = join(client, host, "  Alice  ")
    screen = join(client, host, "Screen", "ecran-principal")
    room = room_manager.get_room(host["code"])
    identities = (host, alice, screen)
    assert len({identity["sessionToken"] for identity in identities}) == 3
    for identity in identities:
        token = identity["sessionToken"]
        assert str(uuid.UUID(identity["localPlayerId"])) == identity["localPlayerId"]
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
        assert len(base64.urlsafe_b64decode(token + "=")) == 32
        assert room.proofs[identity["localPlayerId"]] == hashlib.sha256(token.encode()).digest()
        assert token not in repr(room)
        assert token != identity["localPlayerId"]
    assert [p["name"] for p in alice["state"]["players"]] == ["Host", "Alice"]
    assert all(not p["connected"] for p in alice["state"]["players"])
    assert screen["localPlayerId"] not in {p["id"] for p in screen["state"]["players"]}
    with participants(client, *identities) as (sockets, _):
        command(sockets[0], "theme:add", {"label": "  Cinema  "})
        for socket in sockets:
            state = sync(socket)
            assert state["themes"][0]["label"] == "Cinema"
            for identity in identities:
                assert identity["sessionToken"] not in json.dumps(state)
            assert "sessionToken" not in json.dumps(state)
        for identity in identities:
            response = resume(client, identity)
            assert set(response.json()) == {"code", "localPlayerId", "role", "state"}
            assert response.headers["cache-control"] == "no-store"
            for owner in identities:
                assert owner["sessionToken"] not in response.text
    for identity in identities:
        assert identity["sessionToken"] not in caplog.text


@pytest.mark.parametrize("attack", ["wrong-token", "other-player-token", "unknown-id", "other-room-token"])
def test_public_uuid_does_not_authorize_rest_or_ws(client, attack):
    host = create(client)
    alice = join(client, host)
    stolen = proof(host)
    if attack == "wrong-token":
        stolen["sessionToken"] = TOKEN
    elif attack == "other-player-token":
        stolen["sessionToken"] = alice["sessionToken"]
    elif attack == "unknown-id":
        stolen["localPlayerId"] = str(uuid.uuid4())
    else:
        stolen["sessionToken"] = create(client, "Other")["sessionToken"]
    room = room_manager.get_room(host["code"])
    before = dict(room.proofs)
    response = post(client, f"/api/rooms/{host['code']}/join", stolen)
    http_error(response, 401, "session_revoked")
    assert response.json()["detail"]["message"] == "Session unavailable."
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as socket:
        silent(socket)
        command(socket, "session:auth", stolen)
        terminal(socket, "session_revoked", 4401, "Session unavailable.")
    assert room.proofs == before
    assert not room.connections
    assert all(not player.connected for player in room.state.players)


@pytest.mark.parametrize("active", [False, True])
def test_resume_changes_no_presence_proof_or_broadcast(client, active):
    host = create(client)
    alice = join(client, host)
    with ExitStack() as stack:
        observer, _ = stack.enter_context(connected(client, host))
        if active:
            player_socket, state = stack.enter_context(connected(client, alice))
            assert sync(observer) == state
        room = room_manager.get_room(host["code"])
        before = (room.state, dict(room.proofs), dict(room.connections), room.idle_since)
        result = resume(client, {**alice, "code": alice["code"].lower()})
        assert result.status_code == 200
        assert set(result.json()) == {"code", "localPlayerId", "role", "state"}
        assert result.json()["code"] == host["code"]
        player = next(p for p in result.json()["state"]["players"] if p["id"] == alice["localPlayerId"])
        assert player["connected"] is active
        assert (room.state, room.proofs, room.connections, room.idle_since) == before
        silent(observer)
        if active:
            silent(player_socket)
        command(observer, "theme:add", {"label": "Marker"})
        assert sync(observer)["themes"][0]["label"] == "Marker"


def test_latest_socket_wins_and_old_cleanup_cannot_detach_replacement(client):
    host = create(client)
    alice = join(client, host)
    with connected(client, host) as (observer, _):
        with connected(client, alice) as (old, _):
            sync(observer)
            with connected(client, alice) as (new, state):
                assert sync(observer) == state
                assert all(p["connected"] for p in state["players"])
                terminal(old, "session_replaced", 4409, "Session opened elsewhere.")
                command(old, "player:rename", {"name": "Stale"})
                old.close()
                command(new, "player:rename", {"name": "Current"})
                state = sync(new)
                assert sync(observer) == state
                player = next(p for p in state["players"] if p["id"] == alice["localPlayerId"])
                assert player["name"] == "Current" and player["connected"] is True
                silent(observer)
                assert resume(client, alice).status_code == 200


def test_transfer_updates_live_permissions_without_rotating_proofs(client):
    host = create(client)
    alice = join(client, host)
    with participants(client, host, alice) as (sockets, _):
        old, new = sockets
        digests = dict(room_manager.get_room(host["code"]).proofs)
        command(old, "presenter:transfer", {"targetPlayerId": alice["localPlayerId"]})
        state = sync(old, {**host, "role": "joueur"})
        assert sync(new, {**alice, "role": "presentateur"}) == state
        assert [p["isPresenter"] for p in state["players"]] == [False, True]
        command(old, "theme:add", {"label": "Denied"})
        error(old, "forbidden_role")
        silent(new)
        command(new, "theme:add", {"label": "Allowed"})
        assert sync(old)["themes"][0]["label"] == "Allowed"
        assert sync(new)["themes"][0]["label"] == "Allowed"
        assert room_manager.get_room(host["code"]).proofs == digests
        assert resume(client, host).json()["role"] == "joueur"
        assert resume(client, alice).json()["role"] == "presentateur"


def test_removal_terminal_alias_and_revocation_on_rest_and_reconnect(client):
    host = create(client)
    alice = join(client, host)
    with participants(client, host, alice) as (sockets, _):
        presenter, player = sockets
        command(presenter, "player:remove", {"index": 1})
        terminal(player, "player_kicked", 4403, "You were removed from the room.", "player:kicked")
        assert [p["id"] for p in sync(presenter)["players"]] == [host["localPlayerId"]]
        room = room_manager.get_room(host["code"])
        for table in (room.proofs, room.roles, room.names, room.connections):
            assert alice["localPlayerId"] not in table
        http_error(resume(client, alice), 401, "session_revoked")
        with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as rejected:
            command(rejected, "session:auth", proof(alice))
            terminal(rejected, "session_revoked", 4401, "Session unavailable.")
        silent(presenter)


def test_closure_aliases_revoke_all_sessions_and_missing_room_is_terminal(client):
    host = create(client)
    alice = join(client, host)
    screen = join(client, host, "Screen", "ecran-principal")
    room = room_manager.get_room(host["code"])
    with participants(client, host, alice, screen) as (sockets, _):
        command(sockets[0], "room:quit")
        for socket in sockets:
            terminal(socket, "room_closed", 4404, "Room closed or unavailable.", "room:closed")
    assert room.closed and not room.proofs and not room.connections and not room.roles
    assert host["code"] not in room_manager._rooms
    for identity in (host, alice, screen):
        http_error(resume(client, identity), 404, "room_not_found")
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as socket:
        command(socket, "session:auth", proof(host))
        terminal(socket, "room_closed", 4404, "Room closed or unavailable.", "room:closed")


@pytest.mark.parametrize("headers", [
    {}, {"Origin": "null"}, {"Origin": "http://localhost:5173.evil"},
    {"Origin": "http://localhost:5173/"}, {"Origin": "https://localhost:5173"},
    {"Origin": "http://localhost:5174"}, {"Origin": "http://LOCALHOST:5173"},
    {"Origin": "http://localhost:5173,http://localhost:5173"},
    httpx.Headers([("Origin", ORIGIN), ("Origin", ORIGIN)]),
])
def test_origin_requires_single_exact_allowed_value_before_upgrade(client, headers):
    host = create(client)
    with pytest.raises(WebSocketDenialResponse) as exc:
        with client.websocket_connect(f"/ws/{host['code']}", headers=headers):
            pytest.fail("Forbidden Origin upgraded")
    assert exc.value.status_code == 403
    assert exc.value.json()["detail"]["code"] == "forbidden_origin"
    assert "state" not in exc.value.text and host["sessionToken"] not in exc.value.text
    assert not room_manager.get_room(host["code"]).connections
    assert room_manager.preauth_connections == 0


@pytest.mark.parametrize("query", ["local_player_id=public", "sessionToken=secret", "unexpected=1"])
def test_identity_or_proof_query_parameters_are_rejected(client, query):
    host = create(client)
    with pytest.raises(WebSocketDenialResponse) as exc:
        with client.websocket_connect(f"/ws/{host['code']}?{query}", headers=HEADERS):
            pytest.fail("Query-bearing socket upgraded")
    assert exc.value.status_code == 403


BAD_FRAMES = [
    "{", "null", "[]", "1", '"text"', "true", "{}",
    '{"type":"theme:add"}', '{"payload":{}}',
    '{"type":1,"payload":{}}', '{"type":"theme:add","payload":null}',
    '{"type":"theme:add","payload":[]}',
    '{"type":"theme:add","payload":{},"extra":1}',
    '{"type":"unknown","payload":{}}', b'{"type":"game:start","payload":{}}',
]


@pytest.mark.parametrize("frame", BAD_FRAMES)
def test_invalid_first_message_closes_without_room_data(client, frame):
    host = create(client)
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as socket:
        silent(socket)
        (socket.send_bytes if isinstance(frame, bytes) else socket.send_text)(frame)
        closed(socket, 1008, "invalid_payload")
    assert not room_manager.get_room(host["code"]).connections
    assert room_manager.preauth_connections == 0


@pytest.mark.parametrize("payload", [
    {}, {"localPlayerId": PID}, {"sessionToken": TOKEN},
    {"localPlayerId": PID, "sessionToken": TOKEN, "extra": 1},
    {"localPlayerId": PID.upper(), "sessionToken": TOKEN},
    {"localPlayerId": PID, "sessionToken": "A" * 42 + "B"},
    {"localPlayerId": False, "sessionToken": TOKEN},
])
def test_auth_payload_is_exact_and_strict(client, payload):
    host = create(client)
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as socket:
        command(socket, "session:auth", payload)
        closed(socket, 1008, "invalid_payload")


def test_bad_authenticated_frames_are_targeted_and_socket_remains_usable(client):
    host = create(client)
    screen = join(client, host, "Observer", "ecran-principal")
    with participants(client, host, screen) as (sockets, state):
        actor, observer = sockets
        for frame in BAD_FRAMES:
            (actor.send_bytes if isinstance(frame, bytes) else actor.send_text)(frame)
            error(actor)
        command(actor, "session:auth", proof(host))
        error(actor)
        assert resume(client, host).json()["state"] == state
        silent(observer)
        command(actor, "theme:add", {"label": "Still usable"})
        assert sync(actor)["themes"][0]["label"] == "Still usable"
        assert sync(observer)["themes"][0]["label"] == "Still usable"


INVALID_COMMANDS = [
    ("theme:add", {}), ("theme:add", {"label": " "}),
    ("theme:add", {"label": 1}), ("theme:add", {"label": "x" * 101}),
    ("theme:add", {"label": "Good", "extra": 1}),
    ("player:rename", {"name": None}), ("player:rename", {"name": False}),
    ("player:rename", {"name": " "}), ("player:rename", {"name": "x" * 25}),
    ("player:set_avatar", {"avatar": 1}), ("player:set_avatar", {"avatar": "unknown"}),
    ("player:set_avatar", {"avatar": "alice", "targetPlayerId": PID}),
    ("presenter:transfer", {"targetPlayerId": PID.upper()}),
    ("presenter:transfer", {"targetPlayerId": 1}),
    ("presenter:transfer", {"targetPlayerId": "not-a-uuid"}),
]
INVALID_COMMANDS += [(event, {"index": value})
                     for event in ("theme:remove", "theme:select", "player:remove")
                     for value in (True, False, 0.0, "0", -1, 999, None, [], {})]
INVALID_COMMANDS += [(event, {"extra": 1}) for event in (
    "game:start", "choice:reveal", "timer:start", "answer:good", "answer:bad", "answer:pass",
    "game:reset", "game:end_early", "room:quit", "answer:continue", "answer:vault",
)]


@pytest.mark.parametrize("event,payload", INVALID_COMMANDS)
def test_command_payloads_never_coerce_or_mutate_and_valid_command_works(client, event, payload):
    host = create(client)
    with connected(client, host) as (socket, _):
        command(socket, "theme:add", {"label": "Original"})
        before = sync(socket)
        command(socket, event, payload)
        error(socket)
        assert resume(client, host).json()["state"] == before
        command(socket, "player:rename", {"name": "  Renamed  "})
        state = sync(socket)
        assert state["players"][0]["name"] == "Renamed"
        assert state["themes"] == before["themes"]


@pytest.mark.parametrize("event,payload", [
    ("player:rename", {"name": "Forbidden"}), ("player:set_avatar", {"avatar": "alice"}),
    ("theme:add", {"label": "Forbidden"}), ("game:start", {}), ("room:quit", {}),
])
def test_screen_cannot_rename_change_avatar_or_mutate_game(client, event, payload):
    host = create(client)
    screen = join(client, host, "Screen", "ecran-principal")
    with participants(client, host, screen) as (sockets, before):
        presenter, display = sockets
        command(display, event, payload)
        error(display, "forbidden_role")
        silent(presenter)
        assert resume(client, screen).json()["state"] == before
        assert room_manager.get_room(host["code"]).names[screen["localPlayerId"]] == "Screen"


def test_room_player_screen_and_theme_capacity_are_atomic(client, monkeypatch):
    monkeypatch.setattr(settings, "max_rooms", 1)
    monkeypatch.setattr(settings, "max_players", 2)
    monkeypatch.setattr(settings, "max_screens", 1)
    monkeypatch.setattr(settings, "max_themes", 1)
    host = create(client)
    alice = join(client, host)
    screen = join(client, host, "Screen", "ecran-principal")
    room = room_manager.get_room(host["code"])
    digests = dict(room.proofs)
    http_error(post(client, "/api/rooms", {"pseudo": "Overflow"}), 503, "capacity_exceeded")
    for role in ("joueur", "ecran-principal"):
        http_error(post(client, f"/api/rooms/{host['code']}/join", {"pseudo": "Overflow", "role": role}),
                   409, "capacity_exceeded")
    assert room.proofs == digests
    assert len(room_manager._rooms) == 1 and len(room.state.players) == 2
    for identity in (host, alice, screen):
        assert resume(client, identity).status_code == 200
    with connected(client, host) as (socket, _):
        command(socket, "theme:add", {"label": "One"})
        before = sync(socket)
        command(socket, "theme:add", {"label": "Two"})
        error(socket, "capacity_exceeded")
        assert resume(client, host).json()["state"] == before
        with connected(client, host) as (replacement, _):
            terminal(socket, "session_replaced", 4409, "Session opened elsewhere.")
            command(replacement, "theme:remove", {"index": 0})
            assert sync(replacement)["themes"] == []


def test_new_players_require_lobby_but_resume_and_screens_work_in_game(client):
    host = create(client)
    alice = join(client, host)
    join(client, host, "Bob")
    with participants(client, host, alice) as (sockets, _):
        command(sockets[0], "theme:add", {"label": "Cinema"})
        for socket in sockets:
            sync(socket)
        command(sockets[0], "game:start")
        for socket in sockets:
            assert sync(socket)["phase"] == "selection-pending"
        assert resume(client, alice).status_code == 200
        room = room_manager.get_room(host["code"])
        before = dict(room.proofs)
        http_error(post(client, f"/api/rooms/{host['code']}/join", {"pseudo": "Late"}),
                   409, "invalid_phase")
        assert room.proofs == before
        screen = join(client, host, "Late screen", "ecran-principal")
        assert screen["state"]["phase"] == "selection-pending"
        assert len(screen["state"]["players"]) == 3


def test_rest_body_limit_counts_raw_bytes_before_json_decoding(client, monkeypatch):
    monkeypatch.setattr(settings, "max_rest_body_bytes", 64)
    exact = b'{"pseudo":"Host"}' + b" " * 47
    assert len(exact) == 64
    response = client.post("/api/rooms", content=exact, headers=HEADERS)
    assert response.status_code == 200
    host = response.json()
    for path in ("/api/rooms", f"/api/rooms/{host['code']}/join"):
        for content in (exact + b" ", b"x" * 65, "\u00e9" * 33):
            http_error(client.post(path, content=content, headers=HEADERS), 413, "payload_too_large")
    assert len(room_manager._rooms) == 1
    assert len(room_manager.get_room(host["code"]).proofs) == 1


@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize("binary", [False, True])
def test_ws_oversize_closes_1009_before_or_after_auth(client, monkeypatch, authenticated, binary):
    host = create(client)
    monkeypatch.setattr(settings, "max_message_bytes", 256)
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as socket:
        if authenticated:
            command(socket, "session:auth", proof(host))
            sync(socket)
        if binary:
            socket.send_bytes(b"x" * 257)
        else:
            # 129 code points, but 258 UTF-8 bytes.
            socket.send_text("\u00e9" * 129)
        closed(socket, 1009)


def test_ws_message_at_byte_limit_is_accepted(client, monkeypatch):
    host = create(client)
    monkeypatch.setattr(settings, "max_message_bytes", 256)
    with connected(client, host) as (socket, _):
        message = json.dumps({"type": "theme:add", "payload": {"label": "Boundary"}})
        socket.send_text(message + " " * (256 - len(message.encode())))
        assert sync(socket)["themes"][0]["label"] == "Boundary"


def test_auth_timeout_releases_reservation_without_presence_or_data(client, monkeypatch):
    host = create(client)
    monkeypatch.setattr(settings, "auth_timeout_seconds", .05)
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as socket:
        closed(socket, 4408, "auth_timeout")
    assert room_manager.preauth_connections == 0
    assert not room_manager.authenticated_connections
    assert not room_manager.get_room(host["code"]).connections
    with connected(client, host) as (_, state):
        assert state["players"][0]["connected"] is True


def test_preauth_capacity_rejects_upgrade_and_releases_after_timeout(client, monkeypatch):
    host = create(client)
    monkeypatch.setattr(settings, "max_preauth_connections", 1)
    monkeypatch.setattr(settings, "auth_timeout_seconds", .2)
    with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS) as waiting:
        with pytest.raises(WebSocketDenialResponse) as exc:
            with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS):
                pytest.fail("Preauth capacity exceeded")
        assert exc.value.status_code == 429
        closed(waiting, 4408, "auth_timeout")
    assert room_manager.preauth_connections == 0
    with connected(client, host):
        pass


def test_authenticated_capacity_does_not_evict_existing_socket(client, monkeypatch):
    host = create(client)
    monkeypatch.setattr(settings, "max_authenticated_connections", 1)
    with connected(client, host) as (original, _):
        with pytest.raises(WebSocketDenialResponse) as rejected:
            with client.websocket_connect(f"/ws/{host['code']}", headers=HEADERS):
                pytest.fail("Authenticated capacity must reject before upgrade")
        assert rejected.value.status_code == 429
        command(original, "theme:add", {"label": "Still active"})
        assert sync(original)["themes"][0]["label"] == "Still active"


def test_rest_bucket_shared_across_create_join_resume_ignores_forwarded_ip(client, monkeypatch):
    host = create(client)
    now = [0.0]
    monkeypatch.setattr(rooms, "rest_bucket", TokenBucket(1, 2, clock=lambda: now[0]))
    assert resume(client, host).status_code == 200
    http_error(post(client, "/api/rooms", {}), 422, "invalid_payload")
    for path, payload in (("/api/rooms", {"pseudo": "Other"}),
                          (f"/api/rooms/{host['code']}/join", {"pseudo": "Alice"}),
                          (f"/api/rooms/{host['code']}/join", proof(host))):
        response = client.post(path, json=payload, headers={**HEADERS, "X-Forwarded-For": "203.0.113.1"})
        http_error(response, 429, "rate_limited")
        assert response.headers["retry-after"] == "1"
    assert len(room_manager._rooms) == 1
    assert len(room_manager.get_room(host["code"]).proofs) == 1
    now[0] += 1
    assert resume(client, host).status_code == 200


def test_upgrade_bucket_rejects_before_auth_and_refills(client, monkeypatch):
    host = create(client)
    now = [0.0]
    monkeypatch.setattr(ws_api, "upgrade_bucket", TokenBucket(1, 1, clock=lambda: now[0]))
    with connected(client, host) as (socket, _):
        with pytest.raises(WebSocketDenialResponse) as exc:
            with client.websocket_connect(f"/ws/{host['code']}", headers={**HEADERS, "X-Forwarded-For": "203.0.113.2"}):
                pytest.fail("Rate-limited upgrade accepted")
        assert exc.value.status_code == 429
        assert exc.value.json()["detail"]["code"] == "rate_limited"
        assert "state" not in exc.value.text
        command(socket, "theme:add", {"label": "Unaffected"})
        assert sync(socket)["themes"][0]["label"] == "Unaffected"
    now[0] += 1
    with connected(client, host):
        pass


def test_command_bucket_counts_invalid_messages_and_does_not_affect_observer(client, monkeypatch):
    host = create(client)
    screen = join(client, host, "Screen", "ecran-principal")
    monkeypatch.setattr(settings, "ws_command_rate_per_second", .001)
    monkeypatch.setattr(settings, "ws_command_rate_burst", 2)
    with participants(client, host, screen) as (sockets, _):
        actor, observer = sockets
        actor.send_text("{")
        error(actor)
        command(actor, "theme:add", {"label": "Only accepted"})
        sync(actor)
        sync(observer)
        command(actor, "theme:add", {"label": "Rate denied"})
        error(actor, "rate_limited")
        closed(actor, 4429, "rate_limited")
        state = sync(observer)
        assert [theme["label"] for theme in state["themes"]] == ["Only accepted"]
        assert state["players"][0]["connected"] is False
        silent(observer)
        command(observer, "theme:add", {"label": "Forbidden"})
        error(observer, "forbidden_role")


def test_global_command_bucket_is_shared_between_sockets(client, monkeypatch):
    host = create(client)
    alice = join(client, host)
    with participants(client, host, alice) as (sockets, _):
        presenter, player = sockets
        monkeypatch.setattr(ws_api, "global_bucket", TokenBucket(.001, 1))
        command(player, "player:rename", {"name": "Updated"})
        sync(player)
        sync(presenter)
        command(presenter, "theme:add", {"label": "Rate denied"})
        error(presenter, "rate_limited")
        closed(presenter, 4429, "rate_limited")
        state = sync(player)
        assert not state["themes"]
        assert state["players"][1]["name"] == "Updated"
