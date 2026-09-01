"""Database repositories with direct SQL/ORM filtering."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.database.models import Order, Profile, ProfileContact
from app.services.profiles import ProfileDraft

REQUEST_NUMBER_OFFSET = 100
ORDER_NUMBER_OFFSET = 5000


@dataclass(frozen=True)
class ProfileFilters:
    gender: str | None = None
    residence: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    marital_status: str | None = None
    occupation: str | None = None
    education: str | None = None
    children_min: int | None = None
    children_max: int | None = None
    limit: int = 20


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, draft: ProfileDraft) -> Profile:
        public = draft.public_data
        contact = draft.private_contact_data
        profile = Profile(
            request_number=None,
            gender=public["gender"],
            name=public.get("name"),
            age=int(public["age"]),
            residence=public["residence"],
            marital_status=public.get("marital_status"),
            children_count=public.get("children_count"),
            occupation=public.get("occupation"),
            education=public.get("education"),
            height=public.get("height"),
            weight=public.get("weight"),
            appearance=public.get("appearance"),
            partner_requirements=public.get("partner_requirements"),
            photo_file_id=public.get("photo_file_id"),
            status="active",
        )
        self.session.add(profile)
        self.session.flush()
        profile.request_number = REQUEST_NUMBER_OFFSET + profile.id
        self.session.add(
            ProfileContact(
                profile_id=profile.id,
                phone=contact.get("phone"),
                telegram_username=contact.get("telegram_username"),
                whatsapp=contact.get("whatsapp"),
            )
        )
        self.session.flush()
        return profile

    def get(self, request_number: int) -> Profile | None:
        return self.session.scalar(select(Profile).where(Profile.request_number == request_number))

    def get_public(self, request_number: int) -> dict | None:
        profile = self.get(request_number)
        return profile_to_dict(profile) if profile is not None else None

    def get_with_contact(self, request_number: int) -> dict | None:
        profile = self.get(request_number)
        if profile is None:
            return None
        contact = self.session.scalar(select(ProfileContact).where(ProfileContact.profile_id == profile.id))
        return profile_to_dict(profile, contact)

    def get_contact(self, request_number: int) -> ProfileContact | None:
        profile = self.get(request_number)
        if profile is None:
            return None
        return self.session.scalar(select(ProfileContact).where(ProfileContact.profile_id == profile.id))

    def latest(self, limit: int = 20, include_inactive: bool = False) -> list[Profile]:
        stmt = select(Profile)
        if not include_inactive:
            stmt = stmt.where(Profile.status.in_(["active", "reserved"]))
        stmt = stmt.order_by(desc(Profile.created_at)).limit(max(1, min(limit, 50)))
        return list(self.session.scalars(stmt).all())

    def search(self, filters: ProfileFilters, include_inactive: bool = False) -> list[Profile]:
        stmt = select(Profile)
        if not include_inactive:
            stmt = stmt.where(Profile.status.in_(["active", "reserved"]))
        if filters.gender:
            stmt = stmt.where(Profile.gender == filters.gender)
        if filters.residence:
            stmt = stmt.where(Profile.residence.ilike(f"%{filters.residence.strip()}%"))
        if filters.age_min is not None:
            stmt = stmt.where(Profile.age >= filters.age_min)
        if filters.age_max is not None:
            stmt = stmt.where(Profile.age <= filters.age_max)
        if filters.marital_status:
            stmt = stmt.where(Profile.marital_status.ilike(f"%{filters.marital_status.strip()}%"))
        if filters.occupation:
            stmt = stmt.where(Profile.occupation.ilike(f"%{filters.occupation.strip()}%"))
        if filters.education:
            stmt = stmt.where(Profile.education.ilike(f"%{filters.education.strip()}%"))
        if filters.children_min is not None:
            stmt = stmt.where(Profile.children_count >= filters.children_min)
        if filters.children_max is not None:
            stmt = stmt.where(Profile.children_count <= filters.children_max)
        stmt = stmt.order_by(Profile.age.asc(), desc(Profile.created_at)).limit(max(1, min(filters.limit, 50)))
        return list(self.session.scalars(stmt).all())

    def update(self, request_number: int, changes: dict) -> Profile | None:
        profile = self.get(request_number)
        if profile is None:
            return None
        public_fields = {
            "gender", "name", "age", "residence", "marital_status", "children_count",
            "occupation", "education", "height", "weight", "appearance", "partner_requirements",
            "photo_file_id", "status",
        }
        contact_fields = {"phone", "telegram_username", "whatsapp"}
        contact = self.get_contact(request_number)
        if contact is None:
            contact = ProfileContact(profile_id=profile.id)
            self.session.add(contact)
        for key, value in changes.items():
            if key in public_fields:
                setattr(profile, key, value)
            elif key in contact_fields:
                setattr(contact, key, value)
        self.session.flush()
        return profile

    def disable(self, request_number: int) -> Profile | None:
        return self.update(request_number, {"status": "inactive"})

    def reserve(self, request_number: int) -> Profile | None:
        profile = self.get(request_number)
        if profile is None or profile.status == "inactive":
            return None
        return self.update(request_number, {"status": "reserved"})

    def activate(self, request_number: int) -> Profile | None:
        profile = self.get(request_number)
        if profile is None or profile.status == "inactive":
            return None
        return self.update(request_number, {"status": "active"})

    def delete_requests(self, request_numbers: list[int]) -> int:
        numbers = sorted({int(number) for number in request_numbers if int(number) > 0})
        if not numbers:
            return 0
        profiles = list(self.session.scalars(select(Profile).where(Profile.request_number.in_(numbers))).all())
        if not profiles:
            return 0
        profile_ids = [profile.id for profile in profiles]
        self.session.execute(delete(Order).where(Order.profile_id.in_(profile_ids)))
        self.session.execute(delete(ProfileContact).where(ProfileContact.profile_id.in_(profile_ids)))
        self.session.execute(delete(Profile).where(Profile.id.in_(profile_ids)))
        self.session.flush()
        return len(profiles)

    def delete_all(self) -> int:
        profile_ids = list(self.session.scalars(select(Profile.id)).all())
        if not profile_ids:
            return 0
        self.session.execute(delete(Order).where(Order.profile_id.in_(profile_ids)))
        self.session.execute(delete(ProfileContact).where(ProfileContact.profile_id.in_(profile_ids)))
        self.session.execute(delete(Profile).where(Profile.id.in_(profile_ids)))
        self.session.flush()
        return len(profile_ids)

    def all_profiles(self, include_inactive: bool = True) -> list[dict]:
        stmt = select(Profile).order_by(Profile.id)
        if not include_inactive:
            stmt = stmt.where(Profile.status.in_(["active", "reserved"]))
        return [profile_to_dict(profile, self.get_contact(profile.request_number)) for profile in self.session.scalars(stmt).all()]

    def stats(self) -> dict[str, int]:
        active = self.session.scalar(select(func.count(Profile.id)).where(Profile.status == "active")) or 0
        reserved = self.session.scalar(select(func.count(Profile.id)).where(Profile.status == "reserved")) or 0
        inactive = self.session.scalar(select(func.count(Profile.id)).where(Profile.status == "inactive")) or 0
        female = self.session.scalar(select(func.count(Profile.id)).where(Profile.gender == "female", Profile.status.in_(["active", "reserved"]))) or 0
        male = self.session.scalar(select(func.count(Profile.id)).where(Profile.gender == "male", Profile.status.in_(["active", "reserved"]))) or 0
        pending_orders = self.session.scalar(select(func.count(Order.id)).where(Order.status.in_(["pending_payment", "pending_review"]))) or 0
        paid_orders = self.session.scalar(select(func.count(Order.id)).where(Order.status == "paid")) or 0
        return {"active": int(active), "reserved": int(reserved), "inactive": int(inactive), "female": int(female), "male": int(male), "pending_orders": int(pending_orders), "paid_orders": int(paid_orders)}


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_contact_request(self, user_telegram_id: int, request_number: int, amount: Decimal, payment_method: str) -> Order | None:
        profile = ProfileRepository(self.session).get(request_number)
        if profile is None or profile.status != "active":
            return None
        order = Order(
            order_number=None,
            user_telegram_id=user_telegram_id,
            profile_id=profile.id,
            amount_usd=amount,
            payment_method=payment_method,
            status="pending_payment",
        )
        self.session.add(order)
        self.session.flush()
        order.order_number = ORDER_NUMBER_OFFSET + order.id
        self.session.flush()
        return order

    def get(self, order_number: int) -> Order | None:
        return self.session.scalar(select(Order).where(Order.order_number == order_number))

    def list_pending(self, limit: int = 30) -> list[Order]:
        stmt = select(Order).where(Order.status.in_(["pending_payment", "pending_review"])).order_by(desc(Order.created_at)).limit(max(1, min(limit, 50)))
        return list(self.session.scalars(stmt).all())

    def set_transaction_id(self, order_number: int, transaction_id: str) -> Order | None:
        order = self.get(order_number)
        if order is None:
            return None
        order.transaction_id = transaction_id.strip()
        order.status = "pending_review"
        self.session.flush()
        return order

    def confirm_payment(self, order_number: int) -> Order | None:
        order = self.get(order_number)
        if order is None:
            return None
        if order.status != "pending_review":
            return order
        order.status = "paid"
        self.session.flush()
        return order

    def reject_payment(self, order_number: int, notes: str | None = None) -> Order | None:
        order = self.get(order_number)
        if order is None:
            return None
        order.status = "rejected"
        order.notes = notes
        self.session.flush()
        return order


def export_all_data(session: Session) -> dict:
    profiles = ProfileRepository(session).all_profiles(True)
    orders = []
    for order in session.scalars(select(Order).order_by(Order.id)).all():
        orders.append({
            "order_number": order.order_number,
            "user_telegram_id": order.user_telegram_id,
            "profile_request_number": order.profile.request_number,
            "amount_usd": str(order.amount_usd),
            "payment_method": order.payment_method,
            "status": order.status,
            "transaction_id": order.transaction_id,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        })
    return {"profiles": profiles, "orders": orders}


def profile_to_dict(profile: Profile, contact: ProfileContact | None = None) -> dict:
    result = {
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
        "height": profile.height,
        "weight": profile.weight,
        "appearance": profile.appearance,
        "partner_requirements": profile.partner_requirements,
        "photo_file_id": profile.photo_file_id,
        "status": profile.status,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
    if contact is not None:
        result.update({"phone": contact.phone, "telegram_username": contact.telegram_username, "whatsapp": contact.whatsapp})
    return result
