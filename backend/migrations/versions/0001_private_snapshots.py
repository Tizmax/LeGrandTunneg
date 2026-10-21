"""Add private snapshot, scoped session and append-only event archives.

Revision ID: 0001_private_snapshots
Revises: None
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001_private_snapshots"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rooms",
        sa.Column("room_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(4), nullable=False),
        sa.Column("status", sa.String(7), nullable=False),
        sa.Column("game_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.BigInteger, nullable=False),
        sa.Column("write_id", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("idle_deadline_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_liveness_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="room_revision_positive"),
        sa.CheckConstraint("status IN ('live', 'closed', 'expired')", name="room_status"),
        sa.CheckConstraint("(status = 'live') = (closed_at IS NULL)", name="room_closure"),
        sa.CheckConstraint("code ~ '^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{4}$'", name="room_code"),
    )
    op.create_index("live_room_code_unique", "rooms", ["code"], unique=True,
                    postgresql_where=sa.text("status = 'live'"))
    op.create_table(
        "snapshots",
        sa.Column("room_id", pg.UUID(as_uuid=True), sa.ForeignKey("rooms.room_id"), primary_key=True),
        sa.Column("revision", sa.BigInteger, primary_key=True),
        sa.Column("game_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("write_id", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("format_version", sa.Integer, nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.CheckConstraint("revision >= 1", name="snapshot_revision_positive"),
        sa.CheckConstraint("format_version = 1", name="snapshot_format"),
    )
    op.create_table(
        "sessions",
        sa.Column("room_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision", sa.BigInteger, primary_key=True),
        sa.Column("participant_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("proof_digest", sa.LargeBinary(32), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(7), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["room_id", "revision"], ["snapshots.room_id", "snapshots.revision"]),
        sa.CheckConstraint("octet_length(proof_digest) = 32", name="proof_digest_length"),
        sa.CheckConstraint("role IN ('presentateur', 'joueur', 'ecran-principal')", name="session_role"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="session_status"),
        sa.CheckConstraint("(status = 'revoked') = (revoked_at IS NOT NULL)", name="session_revocation"),
    )
    op.create_table(
        "events",
        sa.Column("event_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("room_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.BigInteger, nullable=False),
        sa.Column("game_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True)),
        sa.Column("target_id", pg.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(["room_id", "revision"], ["snapshots.room_id", "snapshots.revision"]),
        sa.UniqueConstraint("room_id", "revision", name="one_event_per_revision"),
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported; use compatible code or a separately validated restore.")
