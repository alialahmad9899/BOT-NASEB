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


def public_profile(name="آية", age=24, residence="دمشق"):
    return {
        "gender": "female",
        "name": name,
        "age": age,
        "residence": residence,
        "marital_status": "عزباء",
        "occupation": "مدرسة",
    }


def test_order_starts_pending_payment_and_admin_can_confirm_manually():
    with make_session() as session:
        profile = ProfileRepository(session).create(ProfileDraft(public_data=public_profile(), private_contact_data={"phone": "0900000000"}))
        session.commit()
        orders = OrderRepository(session)
        order = orders.create_contact_request(777, profile.request_number, Decimal("5.00"), "شام كاش")
        assert order.status == "pending_payment"
        assert order.amount_usd == Decimal("5.00")
        confirmed = orders.confirm_payment(order.order_number)
        assert confirmed.status == "paid"
        assert confirmed.transaction_id is None


def test_contact_order_number_is_assigned_without_shared_zero_placeholder():
    with make_session() as session:
        profile = ProfileRepository(session).create(ProfileDraft(public_data=public_profile("نور", 23, "حمص"), private_contact_data={"phone": "0922334455"}))
        session.commit()
        order = OrderRepository(session).create_contact_request(778, profile.request_number, Decimal("5.00"), "شام كاش")
        assert order.order_number is not None
        assert order.order_number != 0


def test_pending_order_summary_is_safe_to_use_after_session_closes():
    with make_session() as session:
        profile = ProfileRepository(session).create(ProfileDraft(public_data=public_profile("ريم", 26, "حلب"), private_contact_data={"phone": "0933445566"}))
        session.commit()
        order = OrderRepository(session).create_contact_request(779, profile.request_number, Decimal("5.00"), "شام كاش")
        session.commit()
        summaries = OrderRepository(session).list_pending_summaries()
        assert summaries[0]["order_number"] == order.order_number
        assert summaries[0]["profile_request_number"] == profile.request_number
        assert summaries[0]["status"] == "pending_payment"


def test_delete_single_pending_order_does_not_delete_profile():
    with make_session() as session:
        profile = ProfileRepository(session).create(ProfileDraft(public_data=public_profile(), private_contact_data={"phone": "0900000000"}))
        session.commit()
        orders = OrderRepository(session)
        order = orders.create_contact_request(780, profile.request_number, Decimal("5.00"), "شام كاش")
        deleted = orders.delete_order(order.order_number)
        session.commit()
        assert deleted is True
        assert orders.get(order.order_number) is None
        assert ProfileRepository(session).get(profile.request_number) is not None


def test_delete_all_pending_orders_keeps_paid_orders():
    with make_session() as session:
        profile1 = ProfileRepository(session).create(ProfileDraft(public_data=public_profile("سارة", 25, "دمشق"), private_contact_data={"phone": "0900000000"}))
        profile2 = ProfileRepository(session).create(ProfileDraft(public_data=public_profile("نور", 26, "حمص"), private_contact_data={"phone": "0922334455"}))
        profile3 = ProfileRepository(session).create(ProfileDraft(public_data=public_profile("ريم", 27, "حلب"), private_contact_data={"phone": "0933445566"}))
        session.commit()
        orders = OrderRepository(session)
        pending1 = orders.create_contact_request(781, profile1.request_number, Decimal("5.00"), "شام كاش")
        pending2 = orders.create_contact_request(782, profile2.request_number, Decimal("5.00"), "شام كاش")
        paid = orders.create_contact_request(783, profile3.request_number, Decimal("5.00"), "شام كاش")
        paid = orders.confirm_payment(paid.order_number)
        session.commit()
        count = orders.delete_pending()
        session.commit()
        assert count == 2
        assert orders.get(pending1.order_number) is None
        assert orders.get(pending2.order_number) is None
        assert orders.get(paid.order_number) is not None
        assert orders.get(paid.order_number).status == "paid"
