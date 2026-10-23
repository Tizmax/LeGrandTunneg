"""Strict injected repository double. Not a Postgres or durability proof."""

from app.persistence.codec import decode, encode
from app.persistence.store import PostgresStore, RevisionConflict
from app.rooms.manager import RoomManager


class StrictStore:
    def __init__(self):
        self.heads = {}
        self.archives = []
        self.events = []

    async def check(self):
        pass

    async def close(self):
        pass

    async def load_live(self):
        return tuple(s for s in self.heads.values() if s.status == "live")

    async def write(self, candidate, expected_revision, event):
        candidate = decode(encode(candidate))
        previous = self.heads.get(candidate.room_id)
        if (previous.revision if previous else 0) != expected_revision:
            raise RevisionConflict()
        assert candidate.revision == expected_revision + 1
        if previous:
            PostgresStore._validate_transition(previous, candidate, event)
        else:
            assert event.kind == "room:create"
            assert not any(s.code == candidate.code and s.status == "live" for s in self.heads.values())
        self.heads[candidate.room_id] = candidate
        self.archives.append(candidate)
        if event is not None:
            self.events.append(event)

    async def reconcile(self, candidate, expected_revision):
        saved = self.heads.get(candidate.room_id)
        if saved == candidate:
            return "committed"
        if saved and expected_revision > 0 and saved.revision == expected_revision:
            return "not_committed"
        return "blocked"


def manager_for_test(**kwargs):
    manager = RoomManager(StrictStore(), **kwargs)
    manager.started = True
    return manager


def transport_app():
    from app.main import create_app

    return create_app(store=StrictStore())
