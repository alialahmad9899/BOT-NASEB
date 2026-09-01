import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, Order
from app.database.repositories import ProfileRepository
from app.handlers.payment import WHATSAPP_CONFIRM, payment_whatsapp_confirm, payment_whatsapp_text
from app.services.profiles import ProfileDraft


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def make_profile(session):
    profile = ProfileRepository(session).create(ProfileDraft(
        public_data={
            "gender": "female",
            "name": "آية",
            "age": 25,
            "residence": "دمشق",
            "marital_status": "عزباء",
        },
        private_contact_data={"phone": "0900000000"},
    ))
    session.commit()
    return profile


def make_context(session):
    return SimpleNamespace(
        user_data={"payment_profile_request": 101},
        application=SimpleNamespace(
            bot_data={
                "session_factory": lambda: session,
                "settings": SimpleNamespace(admin_user_ids=frozenset()),
            },
            bot=SimpleNamespace(send_message=AsyncMock()),
        ),
    )


def make_update(text="09 348 883 92"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=777, username="client", first_name="Test", last_name=None),
        effective_message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        callback_query=SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock()),
    )


def test_whatsapp_number_is_confirmed_before_order_is_created():
    with make_session() as session:
        make_profile(session)
        context = make_context(session)
        update = make_update()

        state = asyncio.run(payment_whatsapp_text(update, context))

        assert state == WHATSAPP_CONFIRM
        assert context.user_data["pending_whatsapp"] == "+963934888392"
        assert session.scalar(select(Order)) is None
        update.effective_message.reply_text.assert_awaited_once()
        assert "هل الرقم صحيح؟" in update.effective_message.reply_text.await_args.args[0]


def test_confirmed_whatsapp_creates_contact_order():
    with make_session() as session:
        make_profile(session)
        context = make_context(session)
        context.user_data["pending_whatsapp"] = "+963934888392"
        update = make_update()

        state = asyncio.run(payment_whatsapp_confirm(update, context))

        assert state == -1
        order = session.scalar(select(Order))
        assert order is not None
        assert order.whatsapp == "+963934888392"
        assert order.status == "pending_payment"
        assert context.user_data == {}
