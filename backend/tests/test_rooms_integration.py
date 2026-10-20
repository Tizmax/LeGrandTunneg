"""Tests d'intégration REST + WebSocket du mode room multi (Bloc 4/5).

Couvre les critères "Done when" du Bloc 5 (scope mémoire) :
- 4 clients WS simultanés (1 Présentateur, 2 Joueurs, 1 Écran principal),
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

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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


def _player(state: dict, player_id: str) -> dict:
    return next(p for p in state["players"] if p["id"] == player_id)


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
    assert {p["id"] for p in joined2["state"]["players"]} == {
        presentateur_id, player1_id, player2_id,
    }
    screen = _join_room(client, code, "Projection", "ecran-principal")
    screen_id = screen["localPlayerId"]
    assert screen["role"] == "ecran-principal"
    assert screen_id not in {p["id"] for p in screen["state"]["players"]}

    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws_pres, \
         client.websocket_connect(f"/ws/{code}?local_player_id={player1_id}") as ws_p1, \
         client.websocket_connect(f"/ws/{code}?local_player_id={player2_id}") as ws_p2, \
         client.websocket_connect(f"/ws/{code}?local_player_id={screen_id}") as ws_screen:

        clients = {
            presentateur_id: ws_pres, player1_id: ws_p1,
            player2_id: ws_p2, screen_id: ws_screen,
        }
        roles = {
            presentateur_id: "presentateur", player1_id: "joueur",
            player2_id: "joueur", screen_id: "ecran-principal",
        }

        def sync() -> dict:
            states = []
            for pid, ws in clients.items():
                msg = ws.receive_json()
                assert msg["type"] == "room:state_sync"
                assert msg["payload"]["code"] == code
                assert msg["payload"]["localPlayerId"] == pid
                assert msg["payload"]["role"] == roles[pid]
                states.append(msg["payload"]["state"])
            assert all(s == states[0] for s in states)
            state = states[0]
            assert _player(state, presentateur_id)["isPresenter"] is True
            assert _player(state, presentateur_id)["points"] == 0
            assert all(not _player(state, pid)["isPresenter"] for pid in (player1_id, player2_id))
            assert screen_id not in {p["id"] for p in state["players"]}
            if state["phase"] != "lobby":
                assert state["players"][state["currentPlayerIndex"]]["id"] in (player1_id, player2_id)
            return state

        def action(ws, event: str, payload: dict | None = None) -> dict:
            ws.send_json({"type": event, "payload": payload or {}})
            return sync()

        # Chaque connexion reçoit un state_sync initial avec son propre rôle.
        state = sync()
        assert state["phase"] == "lobby"
        assert _player(state, presentateur_id)["name"] == "Présentateur Paul"
        assert len({p["avatar"] for p in state["players"]}) == 3

        ws_screen.send_json({"type": "game:start", "payload": {}})
        assert ws_screen.receive_json()["payload"]["code"] == "forbidden_role"

        # Présentateur ajoute un thème directement dans le lobby unique
        # (fusion 2026-10-11 : plus de phase 'themes' séparée).
        state = action(ws_pres, "theme:add", {"label": "Cinéma"})
        assert len(state["themes"]) == 1

        state = action(ws_pres, "game:start")
        assert state["phase"] == "selection-pending"
        first_id = state["players"][state["currentPlayerIndex"]]["id"]
        second_id = next(pid for pid in (player1_id, player2_id) if pid != first_id)
        current_player_ws = clients[first_id]
        other_player_ws = clients[second_id]

        for event, payload in (
            ("player:rename", {"name": "Autre nom"}),
            ("player:set_avatar", {"avatar": _player(state, first_id)["avatar"]}),
        ):
            current_player_ws.send_json({"type": event, "payload": payload})
            error = current_player_ws.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "invalid_phase"

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
        assert action(ws_pres, "choice:reveal")["phase"] == "selection"

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

        # Le bon joueur sélectionne le thème -> broadcast à tous, entre dans
        # question-pending (le Présentateur n'a pas encore lancé le chrono).
        state = action(current_player_ws, "theme:select", {"index": 0})
        assert state["phase"] == "tunnel"
        assert state["tunnelSubPhase"] == "question-pending"

        # --- Rejet : jugement de réponse refusé tant que le chrono n'est pas lancé.
        ws_pres.send_json({"type": "answer:good", "payload": {}})
        err = ws_pres.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "invalid_phase"

        # --- Rejet : timer:start refusé pour un Joueur.
        current_player_ws.send_json({"type": "timer:start", "payload": {}})
        err = current_player_ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "forbidden_role"

        # Présentateur a fini de poser sa question -> lance le chrono.
        assert action(ws_pres, "timer:start")["tunnelSubPhase"] == "question"

        # Présentateur juge bonne réponse -> progress_value=1, after-success-pending.
        assert action(ws_pres, "answer:good")["tunnelSubPhase"] == "after-success-pending"

        # --- Rejet : choice:reveal refusé pour un Joueur.
        current_player_ws.send_json({"type": "choice:reveal", "payload": {}})
        err = current_player_ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "forbidden_role"

        assert action(ws_pres, "choice:reveal")["tunnelSubPhase"] == "after-success-open"

        # Le joueur coffre -> crédite des points, repasse à selection-pending.
        state = action(current_player_ws, "answer:vault")
        assert state["phase"] == "selection-pending"
        assert _player(state, first_id)["points"] == 1
        assert _player(state, second_id)["points"] == 0
        assert state["players"][state["currentPlayerIndex"]]["id"] == second_id
        assert state["themes"][0]["validatedSquares"] == 1

        # Le second joueur termine le tunnel : Continuer, puis coffrage auto case 10.
        action(ws_pres, "choice:reveal")
        action(other_player_ws, "theme:select", {"index": 0})
        for square in range(2, 11):
            assert action(ws_pres, "timer:start")["tunnelSubPhase"] == "question"
            state = action(ws_pres, "answer:good")
            assert state["themes"][0]["progressValue"] == square
            if square < 10:
                assert state["tunnelSubPhase"] == "after-success-pending"
                action(ws_pres, "choice:reveal")
                assert action(other_player_ws, "answer:continue")["tunnelSubPhase"] == "question-pending"
        assert state["phase"] == "end"
        assert state["tunnelSubPhase"] is None
        assert state["activeThemeIndex"] is None
        assert state["themes"][0]["completed"] is True
        assert state["themes"][0]["validatedSquares"] == 10
        assert _player(state, first_id)["points"] == 1
        assert _player(state, second_id)["points"] == 22
        assert state["history"] == [
            {"themeLabel": "Cinéma", "playerName": _player(state, first_id)["name"], "pointsGained": 1},
            {"themeLabel": "Cinéma", "playerName": _player(state, second_id)["name"], "pointsGained": 22},
        ]


def test_reconnection_receives_full_state() -> None:
    _reset_rooms()
    client = TestClient(app)
    created = _create_room(client, "Présentateur")
    code = created["code"]
    presentateur_id = created["localPlayerId"]

    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws:
        ws.receive_json()  # état initial
        ws.send_json({"type": "game:start", "payload": {}})
        # game:start échoue silencieusement si <2 joueurs, mais ici on teste
        # juste la reconnexion donc on vérifie une erreur attendue (pas 2 joueurs).
        err = ws.receive_json()
        assert err["type"] == "error"

    # Reconnexion avec le même local_player_id : nouvel état complet renvoyé.
    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws2:
        msg = ws2.receive_json()
        assert msg["type"] == "room:state_sync"
        assert msg["payload"]["localPlayerId"] == presentateur_id
        assert msg["payload"]["role"] == "presentateur"


def test_lobby_avatars_targeted_removal_and_transfer_state() -> None:
    """Contrat public du lobby, pas validation des permissions après transfert (Bloc 13)."""
    from contextlib import ExitStack

    _reset_rooms()
    client = TestClient(app)
    host = _create_room(client, "Paul")
    code, host_id = host["code"], host["localPlayerId"]
    alice = _join_room(client, code, "Alice")
    bob = _join_room(client, code, "Bob")
    screen = _join_room(client, code, "Projection", "ecran-principal")
    alice_id, bob_id, screen_id = (p["localPlayerId"] for p in (alice, bob, screen))

    with ExitStack() as stack:
        sockets = {
            pid: stack.enter_context(client.websocket_connect(f"/ws/{code}?local_player_id={pid}"))
            for pid in (host_id, alice_id, bob_id, screen_id)
        }
        states = [ws.receive_json()["payload"]["state"] for ws in sockets.values()]
        assert all(s == states[0] for s in states)
        state = states[0]
        original = {p["id"]: p.copy() for p in state["players"]}
        used = {p["avatar"] for p in state["players"]}
        free = next(a for a in ("alice", "bob", "charlie", "diana") if a not in used)

        # Le présentateur comme les joueurs peut changer uniquement son avatar.
        sockets[host_id].send_json({"type": "player:set_avatar", "payload": {"avatar": free}})
        for ws in sockets.values():
            state = ws.receive_json()["payload"]["state"]
            assert _player(state, host_id)["avatar"] == free
            assert _player(state, alice_id) == original[alice_id]
            assert _player(state, bob_id) == original[bob_id]
        sockets[alice_id].send_json({"type": "player:set_avatar", "payload": {"avatar": free}})
        error = sockets[alice_id].receive_json()
        assert error["type"] == "error"
        assert error["payload"]["code"] == "invalid_payload"
        sockets[alice_id].send_json({"type": "player:set_avatar", "payload": {"avatar": "not-an-avatar"}})
        assert sockets[alice_id].receive_json()["payload"]["code"] == "invalid_payload"
        sockets[alice_id].send_json({"type": "player:set_avatar", "payload": {"avatar": original[host_id]["avatar"]}})
        for ws in sockets.values():
            state = ws.receive_json()["payload"]["state"]
            assert _player(state, alice_id)["avatar"] == original[host_id]["avatar"]
            assert _player(state, host_id)["avatar"] == free

        bob_index = next(i for i, p in enumerate(state["players"]) if p["id"] == bob_id)
        sockets[alice_id].send_json({"type": "player:remove", "payload": {"index": bob_index}})
        assert sockets[alice_id].receive_json()["payload"]["code"] == "forbidden_role"
        host_index = next(i for i, p in enumerate(state["players"]) if p["id"] == host_id)
        sockets[host_id].send_json({"type": "player:remove", "payload": {"index": host_index}})
        assert sockets[host_id].receive_json()["payload"]["code"] == "invalid_payload"
        sockets[host_id].send_json({"type": "player:remove", "payload": {"index": bob_index}})
        assert sockets[bob_id].receive_json() == {"type": "player:kicked", "payload": {}}
        with pytest.raises(WebSocketDisconnect):
            sockets[bob_id].receive_json()
        del sockets[bob_id]
        for ws in sockets.values():
            state = ws.receive_json()["payload"]["state"]
            assert {p["id"] for p in state["players"]} == {host_id, alice_id}
        # La sortie de la socket retirée peut aussi diffuser la présence inchangée.
        # Une action barrière permet de vider ces notifications avant le transfert.
        sockets[host_id].send_json({"type": "theme:add", "payload": {"label": "Musique"}})
        for ws in sockets.values():
            for _ in range(3):
                state = ws.receive_json()["payload"]["state"]
                if state["themes"]:
                    break
            else:
                pytest.fail("theme:add broadcast not received")
            assert state["themes"][0]["label"] == "Musique"

        sockets[alice_id].send_json({"type": "presenter:transfer", "payload": {"targetPlayerId": host_id}})
        assert sockets[alice_id].receive_json()["payload"]["code"] == "forbidden_role"
        sockets[host_id].send_json({"type": "presenter:transfer", "payload": {"targetPlayerId": alice_id}})
        # Le handler actuel envoie deux synchronisations identiques par destinataire.
        for pid, ws in sockets.items():
            for _ in range(2):
                msg = ws.receive_json()
                assert msg["type"] == "room:state_sync"
                assert msg["payload"]["localPlayerId"] == pid
                assert msg["payload"]["role"] == {
                    host_id: "joueur", alice_id: "presentateur", screen_id: "ecran-principal",
                }[pid]
                state = msg["payload"]["state"]
                assert _player(state, alice_id)["isPresenter"] is True
                assert _player(state, host_id)["isPresenter"] is False
                assert _player(state, host_id)["avatar"] == free
                assert all(p["points"] == 0 for p in state["players"])


def test_player_and_presentateur_can_rename_themselves_in_lobby() -> None:
    """Fusion lobby 2026-10-11 : chacun renomme UNIQUEMENT lui-même, possible
    seulement en lobby (voir engine.rename_player + manager.rename_participant)."""
    _reset_rooms()
    client = TestClient(app)
    created = _create_room(client, "Paul")
    code = created["code"]
    presentateur_id = created["localPlayerId"]
    joined = _join_room(client, code, "Alice")
    player_id = joined["localPlayerId"]

    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws_pres, \
         client.websocket_connect(f"/ws/{code}?local_player_id={player_id}") as ws_p1:
        ws_pres.receive_json()
        ws_p1.receive_json()

        # Le Présentateur renomme lui-même.
        ws_pres.send_json({"type": "player:rename", "payload": {"name": "Paulo"}})
        for ws in (ws_pres, ws_p1):
            msg = ws.receive_json()
            assert _player(msg["payload"]["state"], presentateur_id)["name"] == "Paulo"
            assert _player(msg["payload"]["state"], player_id)["name"] == "Alice"

        # Le joueur renomme lui-même.
        ws_p1.send_json({"type": "player:rename", "payload": {"name": "Alicia"}})
        for ws in (ws_pres, ws_p1):
            msg = ws.receive_json()
            assert _player(msg["payload"]["state"], player_id)["name"] == "Alicia"
            assert _player(msg["payload"]["state"], presentateur_id)["name"] == "Paulo"

        # Un nom vide est refusé, même dans le lobby.
        ws_p1.send_json({"type": "player:rename", "payload": {"name": "   "}})
        err = ws_p1.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "invalid_payload"


def test_player_disconnect_marks_absent_and_reconnect_restores_presence() -> None:
    """Un Joueur qui ferme sa connexion WS reste dans state.players (pour le
    classement final) mais est marqué connected=False (voir
    engine.set_player_connected) — les autres clients déjà connectés doivent
    recevoir le broadcast sans attendre une action quelconque. À la
    reconnexion avec le même local_player_id, il redevient connected=True."""
    _reset_rooms()
    client = TestClient(app)
    created = _create_room(client, "Paul")
    code = created["code"]
    presentateur_id = created["localPlayerId"]
    joined = _join_room(client, code, "Alice")
    player_id = joined["localPlayerId"]

    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws_pres:
        ws_pres.receive_json()

        with client.websocket_connect(f"/ws/{code}?local_player_id={player_id}") as ws_p1:
            ws_p1.receive_json()
            # Alice se (re)connecte : connected=True était déjà la valeur par
            # défaut, donc PAS de broadcast parasite ici (voir app/api/ws.py).

        # La fermeture du `with` ci-dessus clôt la connexion WS d'Alice.
        # Le Présentateur, resté connecté, doit recevoir le state_sync
        # marquant Alice absente.
        msg = ws_pres.receive_json()
        assert msg["type"] == "room:state_sync"
        alice = next(p for p in msg["payload"]["state"]["players"] if p["id"] == player_id)
        assert alice["connected"] is False

        # Alice se reconnecte avec le même local_player_id.
        with client.websocket_connect(f"/ws/{code}?local_player_id={player_id}") as ws_p1_again:
            init = ws_p1_again.receive_json()
            assert _player(init["payload"]["state"], player_id)["connected"] is True
            # Le Présentateur reçoit aussi le broadcast confirmant le retour.
            msg2 = ws_pres.receive_json()
            alice_again = next(
                p for p in msg2["payload"]["state"]["players"] if p["id"] == player_id
            )
            assert alice_again["connected"] is True


def test_game_end_early_returns_everyone_to_lobby() -> None:
    """Le Présentateur peut terminer la partie en cours à tout moment —
    différent de room:quit qui ferme toute la room : ici joueurs et thèmes
    sont conservés, scores remis à zéro, phase='lobby' (voir
    engine.end_game_early)."""
    _reset_rooms()
    client = TestClient(app)
    created = _create_room(client, "Paul")
    code = created["code"]
    presentateur_id = created["localPlayerId"]
    joined1 = _join_room(client, code, "Alice")
    joined2 = _join_room(client, code, "Bob")
    player1_id = joined1["localPlayerId"]
    player2_id = joined2["localPlayerId"]

    with client.websocket_connect(f"/ws/{code}?local_player_id={presentateur_id}") as ws_pres, \
         client.websocket_connect(f"/ws/{code}?local_player_id={player1_id}") as ws_p1, \
         client.websocket_connect(f"/ws/{code}?local_player_id={player2_id}") as ws_p2:
        for ws in (ws_pres, ws_p1, ws_p2):
            ws.receive_json()

        ws_pres.send_json({"type": "theme:add", "payload": {"label": "Cinéma"}})
        for ws in (ws_pres, ws_p1, ws_p2):
            ws.receive_json()

        ws_pres.send_json({"type": "game:start", "payload": {}})
        for ws in (ws_pres, ws_p1, ws_p2):
            ws.receive_json()

        # --- Rejet : un Joueur ne peut pas terminer la partie.
        ws_p1.send_json({"type": "game:end_early", "payload": {}})
        err = ws_p1.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "forbidden_role"

        # Le Présentateur termine la partie en cours.
        ws_pres.send_json({"type": "game:end_early", "payload": {}})
        for ws in (ws_pres, ws_p1, ws_p2):
            msg = ws.receive_json()
            state = msg["payload"]["state"]
            assert state["phase"] == "lobby"
            assert {p["id"] for p in state["players"]} == {presentateur_id, player1_id, player2_id}
            assert len(state["themes"]) == 1
            assert all(p["points"] == 0 for p in state["players"])


def test_unknown_room_rejects_websocket_upgrade() -> None:
    _reset_rooms()
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/ZZZZ?local_player_id=whatever"):
            pass
    assert exc_info.value.code == 1008
