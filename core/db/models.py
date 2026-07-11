"""
SQLAlchemy ORM models for AnonyMus v3.

These models mirror the existing P2P SQLite schema (established by migrations
0001-0010) and will serve as the ground truth once the Alembic migration is
in place. The legacy raw-SQL database module (transports/p2p/database.py) is
kept intact in Phase 2a; both DB layers coexist until Phase 2d.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Common declarative base for all models."""


# ── Users ──────────────────────────────────────────────────────────────────────


class User(Base):
    """Local user profile (one per node)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    onion_address: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    contacts: Mapped[list[Contact]] = relationship(
        "Contact",
        foreign_keys="Contact.owner_onion",
        back_populates="owner",
        lazy="selectin",
    )


# ── Contacts ───────────────────────────────────────────────────────────────────


class Contact(Base):
    """A peer in the local contact list."""

    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("owner_onion", "onion_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_onion: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("users.onion_address", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    onion_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    public_key_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_secret_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    owner: Mapped[User] = relationship(
        "User", foreign_keys=[owner_onion], back_populates="contacts"
    )


# ── Messages ───────────────────────────────────────────────────────────────────


class Message(Base):
    """An end-to-end encrypted message in a direct conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(
        String(64),
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    sender_onion: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recipient_onion: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    ciphertext_b64: Mapped[str] = mapped_column(Text, nullable=False)
    iv_b64: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disappears_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ── Groups ─────────────────────────────────────────────────────────────────────


class Group(Base):
    """A named group (or broadcast channel)."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(
        String(64),
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    founder_onion: Mapped[str] = mapped_column(String(128), nullable=False)
    is_channel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    members: Mapped[list[GroupMember]] = relationship(
        "GroupMember",
        back_populates="group",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list[GroupMessage]] = relationship(
        "GroupMessage", back_populates="group", lazy="noload"
    )


class GroupMember(Base):
    """Membership record linking a contact to a group."""

    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "onion_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    onion_address: Mapped[str] = mapped_column(String(128), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    group: Mapped[Group] = relationship("Group", back_populates="members")


class GroupMessage(Base):
    """A message posted in a group."""

    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(
        String(64),
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    group_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_onion: Mapped[str] = mapped_column(String(128), nullable=False)
    ciphertext_b64: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    group: Mapped[Group] = relationship("Group", back_populates="messages")
