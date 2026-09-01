"""SQLAlchemy models for marriage profiles, private contacts, and manual orders."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_number: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    gender: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    residence: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    marital_status: Mapped[str | None] = mapped_column(String(80), index=True)
    children_count: Mapped[int | None] = mapped_column(Integer, index=True)
    occupation: Mapped[str | None] = mapped_column(String(160), index=True)
    education: Mapped[str | None] = mapped_column(String(200))
    height: Mapped[float | None] = mapped_column(Numeric(5, 2))
    weight: Mapped[float | None] = mapped_column(Numeric(6, 2))
    appearance: Mapped[str | None] = mapped_column(Text)
    partner_requirements: Mapped[str | None] = mapped_column(Text)
    photo_file_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("age >= 18 AND age <= 100", name="ck_profile_age_range"),
        CheckConstraint(
            "children_count IS NULL OR children_count >= 0",
            name="ck_profile_children_count_nonnegative",
        ),
        CheckConstraint(
            "status IN ('active', 'reserved', 'inactive')",
            name="profiles_status_check",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    contact: Mapped["ProfileContact | None"] = relationship(
        back_populates="profile", cascade="all, delete-orphan", uselist=False
    )


class ProfileContact(Base):
    __tablename__ = "profile_contacts"

    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    phone: Mapped[str | None] = mapped_column(String(80))
    telegram_username: Mapped[str | None] = mapped_column(String(120))
    whatsapp: Mapped[str | None] = mapped_column(String(120))

    profile: Mapped[Profile] = relationship(back_populates="contact")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("5.00"))
    payment_method: Mapped[str] = mapped_column(String(80), nullable=False, default="شام كاش")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_payment", index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    profile: Mapped[Profile] = relationship()
