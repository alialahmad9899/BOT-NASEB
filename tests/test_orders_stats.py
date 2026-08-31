from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.database.repositories import OrderRepository, ProfileRepository
from app.services.profiles import ProfileDraft


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_order_starts_pending_payment_and_admin_can_confirm():
    with make_session() as session:
        profiles = ProfileRepository(session)
        profile = profiles.create(
            ProfileDraft(
                public_data={
                    "gender": "female", "name": "آية", "age": 24, "province": "دمشق",
                    "city": "دمشق", "marital_status": "عزباء", "occupation": "مدرسة",
                    "height": None, "weight": None, "description": "", "partner_requirements": "",
                    "photo_file_id": None,
                },
                private_contact_data={"phone": "0900000000"},
            )
        )
        session.commit()
        orders = OrderRepository(session)
        order = orders.create_contact_request(777, profile.request_number, Decimal("5.00"), "شام كاش")
        assert order.status == "pending_payment"
        assert order.amount_usd == Decimal("5.00")
        orders.set_transaction_id(order.order_number, "TX123")
        confirmed = orders.confirm_payment(order.order_number)
        assert confirmed.status == "paid"
        assert confirmed.transaction_id == "TX123"


def test_contact_order_number_is_assigned_without_shared_zero_placeholder():
    with make_session() as session:
        profiles = ProfileRepository(session)
        profile = profiles.create(
            ProfileDraft(
                public_data={"gender": "female", "name": "نور", "age": 23, "province": "حمص"},
                private_contact_data={"phone": "0922334455"},
            )
        )
        session.commit()
        orders = OrderRepository(session)
        order = orders.create_contact_request(778, profile.request_number, Decimal("5.00"), "شام كاش")
        assert order.order_number is not None
        assert order.order_number != 0
