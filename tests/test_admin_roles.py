from app.config import DEFAULT_MANAGER_IDS, PRIMARY_ADMIN_ID, Settings
from app.services.admin_access import build_admin_access
from app.services.admin_meta import ensure_admin_roles, get_admin_roles
from app.database.models import Base
from app.database.admin_models import AdminSetting
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_requested_production_admin_ids_are_seeded_as_owner_and_managers():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        telegram_bot_token="test",
        admin_user_ids=frozenset({PRIMARY_ADMIN_ID, *DEFAULT_MANAGER_IDS}),
        admin_owner_ids=frozenset(),
        admin_manager_ids=frozenset(),
        admin_viewer_ids=frozenset(),
        admin_access=build_admin_access("", "", "", ""),
    )
    with Session(engine) as session:
        roles = ensure_admin_roles(session, settings)
        assert roles[PRIMARY_ADMIN_ID] == "owner"
        for uid in DEFAULT_MANAGER_IDS:
            assert roles[uid] == "manager"


def test_owner_can_be_fixed_but_manager_is_not_promoted():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        telegram_bot_token="test",
        admin_user_ids=frozenset({PRIMARY_ADMIN_ID, *DEFAULT_MANAGER_IDS}),
        admin_access=build_admin_access("", "", "", ""),
    )
    with Session(engine) as session:
        ensure_admin_roles(session, settings)
        roles = get_admin_roles(session, settings)
        assert roles[PRIMARY_ADMIN_ID] == "owner"
        assert roles[1923538306] == "manager"
        assert roles[7824433847] == "manager"
