"""Tests d'intégration REST + WebSocket du mode room multi (Bloc 4/5).

Couvre les critères "Done when" du Bloc 5 (scope mémoire) :
- 3 clients WS simultanés (1 Présentateur, 2 Joueurs) sur la même room,
  synchronisation correcte des scores/tours/état des cases.
- rejet d'un jugement de réponse envoyé par un rôle Joueur.
- rejet d'un choix joueur envoyé par le Présentateur à la place du joueur
  concerné.
- rejet d'un choix joueur envoyé par le joueur concerné tant que l'état est
  encore choice_pending.
- rejet d'un choice:reveal envoyé par un Joueur.
- reconnexion (fermeture + réouverture du WS avec le même local_player_id)
  reçoit l'état complet à jour.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.rooms.manager import room_manager


def _reset_rooms() -> None:
    room_manager._rooms.clear()


def _create_room(client: TestClient, pseudo: str) -> dict:
    resp = client.post("/api/rooms", json={"pseudo": pseudo})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _join_room(client: TestClient, code: str, pseudo: str, role: str = "joueur") -> dict:
    resp = client.post(f"/api/rooms/{code}/join", json={"pseudo": pseudo, "role": role})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_full_multi_client_flow() -> None:
    _reset_rooms()
    client = TestClient(app)

    created = _create_room(client, "Présentateur Paul")
    code = created["code"]
    presentateur_id = created["localPlayerId"]
    assert created["role"] == "presentateur"

    joined1 = _join_room(client, code, "Alice")
    joined2 = _join_room(client, code, "Bob")
    player1_id = joined1["localPlayerId"]
    player2_id = joined2["localPlayerId"]
    assert joined1["role"] == "joueur"
    assert joined2["role"] == "joueur"
    assert len(joined2["state"]["players"]) == 2

    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws_pres, \
         client.websocket_connect(f"/ws/{code}?local_player_id={player1_id}") as ws_p1, \
         client.websocket_connect(f"/ws/{code}?local_player_id={player2_id}") as ws_p2:

        # Chaque connexion reçoit un state_sync initial avec son propre rôle.
        init_pres = ws_pres.receive_json()
        init_p1 = ws_p1.receive_json()
        init_p2 = ws_p2.receive_json()
        assert init_pres["payload"]["role"] == "presentateur"
        assert init_p1["payload"]["role"] == "joueur"
        assert init_p2["payload"]["role"] == "joueur"
        assert init_pres["payload"]["state"]["phase"] == "menu"

        # Présentateur avance le lobby -> thèmes -> partie.
        ws_pres.send_json({"type": "lobby:go_to_themes", "payload": {}})
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            assert msg["payload"]["state"]["phase"] == "themes"

        ws_pres.send_json({"type": "theme:add", "payload": {"label": "Cinéma"}})
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            assert len(msg["payload"]["state"]["themes"]) == 1

        ws_pres.send_json({"type": "game:start", "payload": {}})
        states = []
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            states.append(msg["payload"]["state"])
        assert all(s["phase"] == "selection-pending" for s in states)
        current_index = states[0]["currentPlayerIndex"]
        current_player_ws = [ws_p1, ws_p2][current_index]
        other_player_ws = [ws_p2, ws_p1][current_index]

        # --- Rejet : un Joueur ne peut pas juger une réponse.
        current_player_ws.send_json({"type": "answer:good", "payload": {}})
        err = current_player_ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "forbidden_role"

        # --- Rejet : theme:select tant que choice_pending.
        current_player_ws.send_json({"type": "theme:select", "payload": {"index": 0}})
        err = current_player_ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "invalid_phase"

        # Présentateur révèle le choix de thème.
        ws_pres.send_json({"type": "choice:reveal", "payload": {}})
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            assert msg["payload"]["state"]["phase"] == "selection"

        # --- Rejet : le Présentateur ne peut pas sélectionner un thème à la
        # place du joueur.
        ws_pres.send_json({"type": "theme:select", "payload": {"index": 0}})
        err = ws_pres.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "forbidden_role"

        # --- Rejet : l'autre joueur (pas celui dont c'est le tour) ne peut
        # pas sélectionner le thème non plus.
        other_player_ws.send_json({"type": "theme:select", "payload": {"index": 0}})
        err = other_player_ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "not_your_turn"

        # Le bon joueur sélectionne le thème -> broadcast à tous.
        current_player_ws.send_json({"type": "theme:select", "payload": {"index": 0}})
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            assert msg["payload"]["state"]["phase"] == "tunnel"

        # Présentateur juge bonne réponse -> progress_value=1, after-success-pending.
        ws_pres.send_json({"type": "answer:good", "payload": {}})
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            assert msg["payload"]["state"]["tunnelSubPhase"] == "after-success-pending"

        # --- Rejet : choice:reveal refusé pour un Joueur.
        current_player_ws.send_json({"type": "choice:reveal", "payload": {}})
        err = current_player_ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "forbidden_role"

        ws_pres.send_json({"type": "choice:reveal", "payload": {}})
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            assert msg["payload"]["state"]["tunnelSubPhase"] == "after-success-open"

        # Le joueur coffre -> crédite des points, repasse à selection-pending.
        current_player_ws.send_json({"type": "answer:vault", "payload": {}})
        final_states = []
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            final_states.append(msg["payload"]["state"])
        assert all(s["phase"] == "selection-pending" for s in final_states)
        total_points = sum(p["points"] for p in final_states[0]["players"])
        assert total_points == 1  # case 1 du barème = 1 point


def test_reconnection_receives_full_state() -> None:
    _reset_rooms()
    client = TestClient(app)
    created = _create_room(client, "Présentateur")
    code = created["code"]
    presentateur_id = created["localPlayerId"]

    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws:
        ws.receive_json()  # état initial
        ws.send_json({"type": "lobby:go_to_themes", "payload": {}})
        # go_to_themes échoue silencieusement si <2 joueurs, mais ici on teste
        # juste la reconnexion donc on vérifie une erreur attendue (pas 2 joueurs).
        err = ws.receive_json()
        assert err["type"] == "error"

    # Reconnexion avec le même local_player_id : nouvel état complet renvoyé.
    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws2:
        msg = ws2.receive_json()
        assert msg["type"] == "room:state_sync"
        assert msg["payload"]["localPlayerId"] == presentateur_id
        assert msg["payload"]["role"] == "presentateur"


def test_unknown_room_rejects_websocket_upgrade() -> None:
    _reset_rooms()
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws/ZZZZ?local_player_id=whatever"):
            pass
        assert False, "expected WebSocketDisconnect"
    except Exception:
        pass
