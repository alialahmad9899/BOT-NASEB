"""Repository/helpers for additive Admin V2 metadata, backups, audit and settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.database.admin_models import AdminAuditLog, AdminBackup, AdminSetting, OrderAdminMeta, ProfileAdminMeta
from app.database.models import Order, Profile, ProfileContact


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AuditEntry:
    admin_user_id: int
    action: str
    entity_type: str | None = None
    entity_number: int | None = None
    details: str | None = None


def get_profile_meta(session: Session, profile_id: int, create: bool = True) -> ProfileAdminMeta | None:
    row = session.get(ProfileAdminMeta, profile_id)
    if row is None and create:
        row = ProfileAdminMeta(profile_id=profile_id)
        session.add(row)
        session.flush()
    return row


def get_order_meta(session: Session, order_id: int, create: bool = True) -> OrderAdminMeta | None:
    row = session.get(OrderAdminMeta, order_id)
    if row is None and create:
        order = session.get(Order, order_id)
        if order is None:
            return None
        legacy_payment = "paid" if order.status == "paid" else "rejected" if order.status == "rejected" else "pending"
        row = OrderAdminMeta(order_id=order_id, payment_status=legacy_payment, contact_status="new")
        session.add(row)
        session.flush()
    return row


def backfill_meta(session: Session) -> None:
    profile_ids = list(session.scalars(select(Profile.id)).all())
    for profile_id in profile_ids:
        get_profile_meta(session, int(profile_id), create=True)
    order_ids = list(session.scalars(select(Order.id)).all())
    for order_id in order_ids:
        get_order_meta(session, int(order_id), create=True)
    session.commit()


def log_admin_action(
    session: Session,
    admin_user_id: int,
    action: str,
    entity_type: str | None = None,
    entity_number: int | None = None,
    details: str | dict[str, Any] | None = None,
) -> AdminAuditLog:
    if isinstance(details, dict):
        details_text = json.dumps(details, ensure_ascii=False, separators=(",", ":"))
    else:
        details_text = details
    row = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action[:80],
        entity_type=entity_type,
        entity_number=entity_number,
        details=details_text,
    )
    session.add(row)
    session.flush()
    return row


def list_audit_logs(
    session: Session,
    limit: int = 20,
    admin_user_id: int | None = None,
    action: str | None = None,
) -> list[AdminAuditLog]:
    stmt = select(AdminAuditLog).order_by(desc(AdminAuditLog.created_at)).limit(max(1, min(limit, 100)))
    if admin_user_id is not None:
        stmt = stmt.where(AdminAuditLog.admin_user_id == admin_user_id)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    return list(session.scalars(stmt).all())


def get_setting(session: Session, key: str, default: str) -> str:
    row = session.get(AdminSetting, key)
    if row is None:
        return default
    return row.value


def set_setting(session: Session, key: str, value: str, admin_user_id: int | None = None) -> None:
    row = session.get(AdminSetting, key)
    if row is None:
        row = AdminSetting(key=key, value=value, updated_by_admin_id=admin_user_id)
        session.add(row)
    else:
        row.value = value
        row.updated_by_admin_id = admin_user_id
    session.flush()


def service_price(session: Session) -> Decimal:
    raw = get_setting(session, "service_amount_usd", "5.00")
    try:
        value = Decimal(raw).quantize(Decimal("0.01"))
    except Exception:
        value = Decimal("5.00")
    return max(value, Decimal("0.00"))


def payment_method(session: Session) -> str:
    return get_setting(session, "payment_method", "شام كاش")


def list_backups(session: Session, limit: int = 20) -> list[AdminBackup]:
    stmt = select(AdminBackup).order_by(desc(AdminBackup.created_at)).limit(max(1, min(limit, 100)))
    return list(session.scalars(stmt).all())


def build_snapshot(session: Session) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for profile in session.scalars(select(Profile).order_by(Profile.id)).all():
        contact = session.get(ProfileContact, profile.id)
        meta = session.get(ProfileAdminMeta, profile.id)
        profiles.append({
            "id": profile.id,
            "request_number": profile.request_number,
            "gender": profile.gender,
            "name": profile.name,
            "age": profile.age,
            "residence": profile.residence,
            "marital_status": profile.marital_status,
            "children_count": profile.children_count,
            "occupation": profile.occupation,
            "education": profile.education,
            "height": float(profile.height) if profile.height is not None else None,
            "weight": float(profile.weight) if profile.weight is not None else None,
            "appearance": profile.appearance,
            "partner_requirements": profile.partner_requirements,
            "photo_file_id": profile.photo_file_id,
            "status": profile.status,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            "contact": {
                "phone": contact.phone if contact else None,
                "telegram_username": contact.telegram_username if contact else None,
                "whatsapp": contact.whatsapp if contact else None,
            },
            "admin_meta": {
                "archive_status": meta.archive_status if meta else "active",
                "archive_reason": meta.archive_reason if meta else None,
                "archived_at": meta.archived_at.isoformat() if meta and meta.archived_at else None,
                "publication_status": meta.publication_status if meta else "ready",
                "published_at": meta.published_at.isoformat() if meta and meta.published_at else None,
                "quality_score": meta.quality_score if meta else 0,
                "duplicate_of_request_number": meta.duplicate_of_request_number if meta else None,
                "reserved_at": meta.reserved_at.isoformat() if meta and meta.reserved_at else None,
                "reservation_expires_at": meta.reservation_expires_at.isoformat() if meta and meta.reservation_expires_at else None,
                "reservation_reason": meta.reservation_reason if meta else None,
            },
        })

    orders: list[dict[str, Any]] = []
    for order in session.scalars(select(Order).order_by(Order.id)).all():
        meta = session.get(OrderAdminMeta, order.id)
        orders.append({
            "id": order.id,
            "order_number": order.order_number,
            "user_telegram_id": order.user_telegram_id,
            "profile_request_number": order.profile.request_number if order.profile else None,
            "amount_usd": str(order.amount_usd),
            "payment_method": order.payment_method,
            "status": order.status,
            "whatsapp": order.whatsapp,
            "transaction_id": order.transaction_id,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "admin_meta": {
                "payment_status": meta.payment_status if meta else ("paid" if order.status == "paid" else "rejected" if order.status == "rejected" else "pending"),
                "contact_status": meta.contact_status if meta else "new",
                "contacted_at": meta.contacted_at.isoformat() if meta and meta.contacted_at else None,
                "completed_at": meta.completed_at.isoformat() if meta and meta.completed_at else None,
            },
        })

    settings = {row.key: row.value for row in session.scalars(select(AdminSetting)).all()}
    return {"schema_version": 2, "created_at": utc_now().isoformat(), "profiles": profiles, "orders": orders, "settings": settings}


def create_backup(session: Session, admin_user_id: int, reason: str) -> AdminBackup:
    snapshot = build_snapshot(session)
    row = AdminBackup(
        created_by_admin_id=admin_user_id,
        reason=reason[:200],
        snapshot_json=json.dumps(snapshot, ensure_ascii=False),
    )
    session.add(row)
    session.flush()
    return row


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def restore_snapshot(session: Session, snapshot_json: str) -> dict[str, int]:
    payload = json.loads(snapshot_json)
    profiles_data = payload.get("profiles", [])
    orders_data = payload.get("orders", [])
    settings_data = payload.get("settings", {})

    session.execute(delete(OrderAdminMeta))
    session.execute(delete(ProfileAdminMeta))
    session.execute(delete(Order))
    session.execute(delete(ProfileContact))
    session.execute(delete(Profile))
    session.flush()

    request_to_id: dict[int, int] = {}
    for item in profiles_data:
        profile = Profile(
            request_number=item.get("request_number"),
            gender=item.get("gender") or "",
            name=item.get("name"),
            age=int(item.get("age")),
            residence=item.get("residence") or "",
            marital_status=item.get("marital_status"),
            children_count=item.get("children_count"),
            occupation=item.get("occupation"),
            education=item.get("education"),
            height=item.get("height"),
            weight=item.get("weight"),
            appearance=item.get("appearance"),
            partner_requirements=item.get("partner_requirements"),
            photo_file_id=item.get("photo_file_id"),
            status=item.get("status") or "active",
            created_at=_parse_dt(item.get("created_at")) or utc_now(),
            updated_at=_parse_dt(item.get("updated_at")) or utc_now(),
        )
        session.add(profile)
        session.flush()
        if profile.request_number is not None:
            request_to_id[int(profile.request_number)] = int(profile.id)
        contact = item.get("contact") or {}
        if any(contact.get(key) for key in ("phone", "telegram_username", "whatsapp")):
            session.add(ProfileContact(
                profile_id=profile.id,
                phone=contact.get("phone"),
                telegram_username=contact.get("telegram_username"),
                whatsapp=contact.get("whatsapp"),
            ))
        meta_data = item.get("admin_meta") or {}
        session.add(ProfileAdminMeta(
            profile_id=profile.id,
            archive_status=meta_data.get("archive_status") or "active",
            archive_reason=meta_data.get("archive_reason"),
            archived_at=_parse_dt(meta_data.get("archived_at")),
            publication_status=meta_data.get("publication_status") or "ready",
            published_at=_parse_dt(meta_data.get("published_at")),
            quality_score=int(meta_data.get("quality_score") or 0),
            duplicate_of_request_number=meta_data.get("duplicate_of_request_number"),
            reserved_at=_parse_dt(meta_data.get("reserved_at")),
            reservation_expires_at=_parse_dt(meta_data.get("reservation_expires_at")),
            reservation_reason=meta_data.get("reservation_reason"),
        ))

    order_count = 0
    for item in orders_data:
        request_number = item.get("profile_request_number")
        profile_id = request_to_id.get(int(request_number)) if request_number is not None else None
        if profile_id is None:
            continue
        order = Order(
            order_number=item.get("order_number"),
            user_telegram_id=int(item.get("user_telegram_id")),
            profile_id=profile_id,
            amount_usd=Decimal(str(item.get("amount_usd") or "5.00")),
            payment_method=item.get("payment_method") or "شام كاش",
            status=item.get("status") or "pending_payment",
            whatsapp=item.get("whatsapp"),
            transaction_id=item.get("transaction_id"),
            notes=item.get("notes"),
            created_at=_parse_dt(item.get("created_at")) or utc_now(),
            updated_at=_parse_dt(item.get("updated_at")) or utc_now(),
        )
        session.add(order)
        session.flush()
        meta_data = item.get("admin_meta") or {}
        session.add(OrderAdminMeta(
            order_id=order.id,
            payment_status=meta_data.get("payment_status") or ("paid" if order.status == "paid" else "rejected" if order.status == "rejected" else "pending"),
            contact_status=meta_data.get("contact_status") or "new",
            contacted_at=_parse_dt(meta_data.get("contacted_at")),
            completed_at=_parse_dt(meta_data.get("completed_at")),
        ))
        order_count += 1

    for key, value in settings_data.items():
        set_setting(session, str(key), str(value))
    session.flush()
    return {"profiles": len(profiles_data), "orders": order_count}


def expire_reservations(session: Session, now: datetime | None = None) -> int:
    now = now or utc_now()
    rows = list(session.scalars(select(ProfileAdminMeta).where(ProfileAdminMeta.reservation_expires_at.is_not(None), ProfileAdminMeta.reservation_expires_at <= now)).all())
    count = 0
    for meta in rows:
        profile = session.get(Profile, meta.profile_id)
        if profile and profile.status == "reserved":
            profile.status = "active"
            meta.reservation_expires_at = None
            meta.reserved_at = None
            meta.reservation_reason = None
            count += 1
    session.flush()
    return count


def top_residences(session: Session, limit: int = 5) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Profile.residence, func.count(Profile.id))
        .where(Profile.status.in_(["active", "reserved"]))
        .group_by(Profile.residence)
        .order_by(desc(func.count(Profile.id)))
        .limit(max(1, min(limit, 20)))
    ).all()
    return [(str(residence), int(count)) for residence, count in rows]


def metrics(session: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_week = start_today - timedelta(days=start_today.weekday())
    start_month = start_today.replace(day=1)

    profile_counts = {
        "active": session.scalar(select(func.count(Profile.id)).where(Profile.status == "active")) or 0,
        "reserved": session.scalar(select(func.count(Profile.id)).where(Profile.status == "reserved")) or 0,
        "inactive": session.scalar(select(func.count(Profile.id)).where(Profile.status == "inactive")) or 0,
    }
    archived = session.scalar(select(func.count(ProfileAdminMeta.profile_id)).where(ProfileAdminMeta.archive_status == "archived")) or 0
    profile_counts["archived"] = int(archived)
    profile_counts["today"] = int(session.scalar(select(func.count(Profile.id)).where(Profile.created_at >= start_today)) or 0)
    profile_counts["week"] = int(session.scalar(select(func.count(Profile.id)).where(Profile.created_at >= start_week)) or 0)
    profile_counts["month"] = int(session.scalar(select(func.count(Profile.id)).where(Profile.created_at >= start_month)) or 0)
    profile_counts["female"] = int(session.scalar(select(func.count(Profile.id)).where(Profile.gender == "female", Profile.status.in_(["active", "reserved"]))) or 0)
    profile_counts["male"] = int(session.scalar(select(func.count(Profile.id)).where(Profile.gender == "male", Profile.status.in_(["active", "reserved"]))) or 0)

    pending = int(session.scalar(select(func.count(Order.id)).where(Order.status.in_(["pending_payment", "pending_review"]))) or 0)
    paid = int(session.scalar(select(func.count(Order.id)).where(Order.status == "paid")) or 0)
    rejected = int(session.scalar(select(func.count(Order.id)).where(Order.status == "rejected")) or 0)
    today_orders = int(session.scalar(select(func.count(Order.id)).where(Order.created_at >= start_today)) or 0)
    week_orders = int(session.scalar(select(func.count(Order.id)).where(Order.created_at >= start_week)) or 0)
    month_orders = int(session.scalar(select(func.count(Order.id)).where(Order.created_at >= start_month)) or 0)
    completed = int(session.scalar(select(func.count(OrderAdminMeta.order_id)).where(OrderAdminMeta.contact_status == "completed")) or 0)
    contacted = int(session.scalar(select(func.count(OrderAdminMeta.order_id)).where(OrderAdminMeta.contact_status.in_(["contacted", "opened", "completed"]))) or 0)
    conversion = round((completed / paid) * 100, 1) if paid else 0.0

    return {"profiles": profile_counts, "orders": {"pending": pending, "paid": paid, "rejected": rejected, "today": today_orders, "week": week_orders, "month": month_orders, "contacted": contacted, "completed": completed, "conversion": conversion}, "top_residences": top_residences(session)}
