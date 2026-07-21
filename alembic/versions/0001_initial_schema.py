"""Initial schema — AnonyMus v3 P2P node database

Revision ID: 0001
Revises:
Create Date: 2026-07-11 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("onion_address", sa.String(128), nullable=True, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── contacts ───────────────────────────────────────────────────────────────
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("owner_onion", sa.String(128), nullable=False),
        sa.Column("onion_address", sa.String(128), nullable=False),
        sa.Column("nickname", sa.String(64), nullable=True),
        sa.Column("verified", sa.Boolean, nullable=False, server_default="0"),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("owner_onion", "onion_address", name="uq_contact_pair"),
    )

    # ── messages ───────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("message_id", sa.String(36), primary_key=True),
        sa.Column("sender_onion", sa.String(128), nullable=False),
        sa.Column("recipient_onion", sa.String(128), nullable=False),
        sa.Column("ciphertext_b64", sa.Text, nullable=False),
        sa.Column("iv_b64", sa.String(44), nullable=False),
        sa.Column("sequence_number", sa.Integer, nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivered", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("disappears_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_messages_sender_recipient",
        "messages",
        ["sender_onion", "recipient_onion"],
    )
    op.create_index("ix_messages_sent_at", "messages", ["sent_at"])

    # ── groups ─────────────────────────────────────────────────────────────────
    op.create_table(
        "groups",
        sa.Column("group_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("founder_onion", sa.String(128), nullable=False),
        sa.Column("is_channel", sa.Boolean, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── group_members ──────────────────────────────────────────────────────────
    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("onion_address", sa.String(128), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("group_id", "onion_address", name="uq_group_member"),
    )

    # ── group_messages ─────────────────────────────────────────────────────────
    op.create_table(
        "group_messages",
        sa.Column("message_id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("sender_onion", sa.String(128), nullable=False),
        sa.Column("ciphertext_b64", sa.Text, nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.group_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_group_messages_group_id", "group_messages", ["group_id"])


def downgrade() -> None:
    op.drop_table("group_messages")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_index("ix_messages_sent_at", table_name="messages")
    op.drop_index("ix_messages_sender_recipient", table_name="messages")
    op.drop_table("messages")
    op.drop_table("contacts")
    op.drop_table("users")
