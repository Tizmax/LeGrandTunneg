"""Gestionnaire de rooms en mémoire (process-local), Bloc 5 scope mémoire.

Pas de persistance Postgres dans cette passe (voir Limitations connues de
docs/websocket-protocol.md) : toutes les rooms et leur état de jeu vivent
uniquement dans ce module, perdues si le process serveur redémarre.

Une `Room` regroupe :
- l'état de jeu courant (`app.game.types.GameState`, géré exclusivement via
  `app.game.engine`, jamais muté directement ici) ;
- la table des rôles par `local_player_id` (identité stable du participant,
  indépendante de son éventuelle entrée dans `GameState.players`) ;
- les connexions WebSocket actives par `local_player_id`, pour le broadcast.
"""

from __future__ import annotations

import asyncio
import random
import string
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.game import engine
from app.game.serialize import serialize_state
from app.game.types import GameState

if TYPE_CHECKING:
    from fastapi import WebSocket

# Alphabet sans caractères ambigus (pas de 0/O, 1/I/L) pour des codes de room
# lisibles à l'oral/affichés sur un écran principal projeté.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 4


class RoomNotFoundError(Exception):
    pass


class UnknownParticipantError(Exception):
    """local_player_id non reconnu par cette room (ni rôle ni reconnexion possible)."""


@dataclass
class Room:
    code: str
    state: GameState = field(default_factory=GameState)
    # local_player_id -> rôle (presentateur | joueur | ecran-principal)
    roles: dict[str, engine.Role] = field(default_factory=dict)
    # local_player_id -> pseudo d'affichage (y compris pour presentateur/écran,
    # qui n'apparaissent jamais dans state.players)
    names: dict[str, str] = field(default_factory=dict)
    # local_player_id -> connexion WS active (une seule par participant)
    connections: dict[str, "WebSocket"] = field(default_factory=dict)
    presentateur_id: str | None = None
    # Sérialise les mutations d'état pour éviter les races entre deux messages
    # WS concurrents sur la même room.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def role_of(self, local_player_id: str) -> engine.Role | None:
        return self.roles.get(local_player_id)


class RoomManager:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    def _generate_unique_code(self) -> str:
        for _ in range(100):
            code = "".join(random.choices(_CODE_ALPHABET, k=_CODE_LENGTH))
            if code not in self._rooms:
                return code
        raise RuntimeError("Impossible de générer un code de room unique.")

    def create_room(self, pseudo: str) -> tuple[Room, str]:
        """Crée une room ; le créateur devient Présentateur (pas un joueur)."""
        pseudo = pseudo.strip()
        if not pseudo:
            raise ValueError("Le pseudo ne peut pas être vide.")
        code = self._generate_unique_code()
        room = Room(code=code)
        local_player_id = str(uuid.uuid4())
        room.roles[local_player_id] = "presentateur"
        room.names[local_player_id] = pseudo
        room.presentateur_id = local_player_id
        self._rooms[code] = room
        return room, local_player_id

    def get_room(self, code: str) -> Room:
        room = self._rooms.get(code)
        if room is None:
            raise RoomNotFoundError(code)
        return room

    def join_room(
        self,
        code: str,
        pseudo: str,
        role: engine.Role,
        local_player_id: str | None,
    ) -> tuple[Room, str, engine.Role]:
        """Rejoint une room existante, ou reconnecte un participant connu.

        Si `local_player_id` est fourni et déjà connu de la room, c'est une
        reconnexion : aucun nouveau joueur n'est créé, le rôle existant est
        retourné tel quel (le `role` demandé est alors ignoré).
        """
        room = self.get_room(code)

        if local_player_id and local_player_id in room.roles:
            return room, local_player_id, room.roles[local_player_id]

        pseudo = pseudo.strip()
        if not pseudo:
            raise ValueError("Le pseudo ne peut pas être vide.")
        if role not in ("joueur", "ecran-principal"):
            raise ValueError(
                "Seuls les rôles 'joueur' et 'ecran-principal' peuvent rejoindre une room."
            )

        new_id = str(uuid.uuid4())
        if role == "joueur":
            # Peut lever GameError("invalid_phase", ...) si la partie a déjà
            # quitté le lobby — laissé à l'appelant (route REST) de traduire.
            room.state = engine.add_player(room.state, new_id, pseudo)

        room.roles[new_id] = role
        room.names[new_id] = pseudo
        return room, new_id, role

    def close_room(self, code: str) -> None:
        self._rooms.pop(code, None)

    def attach_connection(
        self, code: str, local_player_id: str, websocket: "WebSocket"
    ) -> Room:
        room = self.get_room(code)
        if local_player_id not in room.roles:
            raise UnknownParticipantError(local_player_id)
        room.connections[local_player_id] = websocket
        return room

    def detach_connection(self, code: str, local_player_id: str) -> None:
        room = self._rooms.get(code)
        if room is None:
            return
        room.connections.pop(local_player_id, None)

    async def broadcast_state(self, code: str) -> None:
        """Pousse `room:state_sync` à toutes les connexions WS actives.

        Nécessaire après toute mutation de `room.state` qui ne passe pas par
        la boucle WS elle-même — notamment `join_room` appelé depuis la route
        REST `POST /api/rooms/{code}/join` : un nouveau joueur ajouté à
        `state.players` doit être vu immédiatement par le Présentateur et les
        autres participants déjà connectés en WS, sans attendre qu'un message
        WS quelconque transite.
        """
        room = self._rooms.get(code)
        if room is None:
            return
        stale: list[str] = []
        for local_player_id, conn in list(room.connections.items()):
            role = room.roles.get(local_player_id)
            if role is None:
                continue
            try:
                await conn.send_json(
                    {
                        "type": "room:state_sync",
                        "payload": {
                            "code": code,
                            "role": role,
                            "localPlayerId": local_player_id,
                            "state": serialize_state(room.state),
                        },
                    }
                )
            except Exception:  # connexion morte, nettoyée après coup
                stale.append(local_player_id)
        for local_player_id in stale:
            room.connections.pop(local_player_id, None)


# Instance process-wide unique, importée par les routes REST et le handler WS.
room_manager = RoomManager()

__all__ = [
    "Room",
    "RoomManager",
    "RoomNotFoundError",
    "UnknownParticipantError",
    "room_manager",
]
