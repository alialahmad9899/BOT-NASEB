from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.database.repositories import OrderRepository, ProfileRepository
from app.keyboards.client import client_payment_keyboard
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


def test_duplicate_pending_contact_request_reuses_existing_order():
    with make_session() as session:
        profile = make_profile(session)
        repo = OrderRepository(session)
        first = repo.create_contact_request(123, profile.request_number, Decimal("5.00"), "شام كاش")
        second = repo.create_contact_request(123, profile.request_number, Decimal("5.00"), "شام كاش")
        assert first.order_number == second.order_number


def test_client_payment_keyboard_has_clear_exit_and_submission_actions():
    callbacks = [button.callback_data for row in client_payment_keyboard().inline_keyboard for button in row]
    assert "client:payment:submit" in callbacks
    assert "client:payment:cancel" in callbacks
    assert "client:menu" in callbacks
