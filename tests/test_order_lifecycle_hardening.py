import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.admin_models import OrderAdminMeta
from app.database.models import Base, Order
from app.database.repositories import OrderRepository, ProfileRepository
from app.handlers import admin_v2
from app.services.profiles import ProfileDraft


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _profile(session):
    return ProfileRepository(session).create(
        ProfileDraft(
            public_data={
                "gender": "female",
                "name": "آية",
                "age": 25,
                "residence": "دمشق",
                "marital_status": "عزباء",
                "children_count": 0,
                "occupation": "مدرسة",
                "education": "جامعي",
                "height": 165,
                "weight": 58,
                "appearance": "جذابة",
                "partner_requirements": "جاد بالزواج",
                "photo_file_id": "photo",
            },
            private_contact_data={"phone": "0900000000"},
        ),
        request_number=200,
    )


def _context(engine):
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "session_factory": lambda: Session(engine),
                "settings": SimpleNamespace(
                    admin_user_ids=frozenset({123}),
                    admin_access=SimpleNamespace(role_for=lambda uid: "owner" if uid == 123 else None),
                ),
            },
            bot=SimpleNamespace(send_message=AsyncMock()),
        ),
    )


def _update(callback_data, user_id=123):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=SimpleNamespace(reply_text=AsyncMock(), text=None),
        callback_query=SimpleNamespace(
            data=callback_data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        ),
    )


def test_order_lifecycle_blocks_invalid_transitions_and_allows_valid_path(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        profile = _profile(session)
        order = Order(
            order_number=5001,
            user_telegram_id=777,
            profile_id=profile.id,
            amount_usd=Decimal("5.00"),
            payment_method="شام كاش",
            status="pending_payment",
            whatsapp="0933111111",
        )
        session.add(order)
        session.flush()
        session.add(OrderAdminMeta(order_id=order.id, payment_status="pending", contact_status="new"))
        session.commit()

        ctx = _context(engine)
        monkeypatch.setattr(admin_v2, "_dashboard_keyboard", lambda: None)
        monkeypatch.setattr(admin_v2, "_require_role", lambda update, context, roles: True)
        monkeypatch.setattr(admin_v2, "_is_admin", lambda update, context: True)
        monkeypatch.setattr(admin_v2, "_role", lambda context, user_id=None: "owner")
        for transition in ("confirm", "contacted", "opened", "complete"):
            update = _update(f"admin:v2:order:{transition}:5001")
            asyncio.run(admin_v2._order_transition(update, ctx, 5001, transition))

        session.expire_all()
        saved = session.scalar(select(Order).where(Order.order_number == 5001))
        meta = session.get(OrderAdminMeta, saved.id)
        assert saved.status == "paid"
        assert meta.payment_status == "paid"
        assert meta.contact_status == "completed"

        update = _update("admin:v2:order:reject:5001")
        asyncio.run(admin_v2._order_transition(update, ctx, 5001, "reject"))
        saved = session.scalar(select(Order).where(Order.order_number == 5001))
        assert saved.status == "paid"
        assert "ما فينا نرفض" in update.callback_query.edit_message_text.await_args.args[0]


def test_processed_order_cannot_enter_delete_confirmation(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        profile = _profile(session)
        session.add(Order(
            order_number=5001,
            user_telegram_id=777,
            profile_id=profile.id,
            amount_usd=Decimal("5.00"),
            payment_method="شام كاش",
            status="paid",
        ))
        session.commit()

        ctx = _context(engine)
        monkeypatch.setattr(admin_v2, "_dashboard_keyboard", lambda: None)
        monkeypatch.setattr(admin_v2, "_require_role", lambda update, context, roles: True)
        update = _update("admin:v2:order:delete:5001")
        result = asyncio.run(admin_v2._delete_order(update, ctx, 5001))

        assert result == admin_v2.END
        assert "ما بينحذف" in update.callback_query.edit_message_text.await_args.args[0]
        assert ctx.user_data == {}


def test_delete_repository_never_deletes_processed_orders():
    engine = _engine()
    with Session(engine) as session:
        profile = _profile(session)
        session.add(Order(
            order_number=5001,
            user_telegram_id=777,
            profile_id=profile.id,
            amount_usd=Decimal("5.00"),
            payment_method="شام كاش",
            status="paid",
        ))
        session.commit()

        assert OrderRepository(session).delete_order(5001) is False
        assert session.query(Order).count() == 1
