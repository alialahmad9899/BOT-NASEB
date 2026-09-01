"""Additive database models for Admin V2.

These tables are intentionally separate from the existing profile/order tables so
Admin V2 can evolve without changing or rewriting existing user data.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProfileAdminMeta(Base):
    __tablename__ = "profile_admin_meta"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    archive_status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    archive_reason: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_status: Mapped[str] = mapped_column(String(24), default="ready", nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_of_request_number: Mapped[int | None] = mapped_column(Integer, index=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reservation_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class OrderAdminMeta(Base):
    __tablename__ = "order_admin_meta"

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    payment_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    contact_status: Mapped[str] = mapped_column(String(24), default="new", nullable=False, index=True)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class AdminBackup(Base):
    __tablename__ = "admin_backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by_admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_number: Mapped[int | None] = mapped_column(Integer, index=True)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


class AdminSetting(Base):
    __tablename__ = "admin_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_admin_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
