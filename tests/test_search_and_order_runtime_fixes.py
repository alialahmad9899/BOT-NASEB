from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, Order, Profile, ProfileContact
from app.handlers.safe_order_views import load_admin_order_detail, load_admin_order_rows, load_client_order_detail, load_client_order_rows
from app.handlers.safe_search import prepare_admin_search_query


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_admin_search_accepts_open_ended_age_and_basic_filters_without_callback():
    query = prepare_admin_search_query("كل بنات حلب عمر 20 وما فوق")
    filters = query["filters"]
    assert filters.gender == "female"
    assert filters.residence == "حلب"
    assert filters.age_min == 20
    assert filters.age_max is None


def test_order_snapshots_are_plain_data_before_session_closes():
    engine = _db()
    with Session(engine) as session:
        profile = Profile(request_number=154, gender="female", name="آية", age=24, residence="حلب", status="active")
        session.add(profile)
        session.flush()
        session.add(ProfileContact(profile_id=profile.id, whatsapp="0933111111"))
        order = Order(
            order_number=5205,
            user_telegram_id=777,
            profile_id=profile.id,
            amount_usd=Decimal("5.00"),
            payment_method="شام كاش",
            status="pending_payment",
            whatsapp="0933111111",
        )
        session.add(order)
        session.commit()

        client_rows = load_client_order_rows(session, 777)
        admin_rows, has_next = load_admin_order_rows(session, 0, "pending")
        client_detail = load_client_order_detail(session, 5205, 777)
        admin_detail = load_admin_order_detail(session, 5205)

    assert client_rows[0]["profile_request_number"] == 154
    assert admin_rows[0]["profile_request_number"] == 154
    assert has_next is False
    assert client_detail["profile_request_number"] == 154
    assert admin_detail["profile_request_number"] == 154
    assert admin_detail["profile"]["name"] == "آية"
