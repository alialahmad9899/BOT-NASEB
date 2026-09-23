import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.database.admin_models import AdminSetting
from app.services.admin_meta import get_admin_roles, save_admin_roles, ensure_admin_roles, PRIMARY_ADMIN_ID


def _context(session, uid=1898025825):
    bot=SimpleNamespace(send_message=AsyncMock())
    settings=SimpleNamespace(admin_access=None, admin_user_ids=frozenset({PRIMARY_ADMIN_ID}))
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={"settings": settings, "session_factory": lambda: session, "bot": bot}
        ),
        effective_user=SimpleNamespace(id=uid),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
        callback_query=SimpleNamespace(
            data="admin:v2:settings:roles",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        ),
    )


def test_default_owner_and_employees_are_seeded_once():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        settings=SimpleNamespace(admin_access=None, admin_user_ids=frozenset({PRIMARY_ADMIN_ID}))
        roles=ensure_admin_roles(session,settings)
        assert roles[1898025825] == "owner"
        assert roles[1923538306] == "manager"
        assert roles[7824433847] == "manager"

        roles.pop(1923538306)
        save_admin_roles(session,roles,1898025825)
        session.commit()

        roles2=ensure_admin_roles(session,settings)
        assert 1923538306 not in roles2


def test_owner_can_manage_and_broadcast_but_employee_cannot():
    from app.handlers import admin_v2

    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        settings=SimpleNamespace(admin_access=None, admin_user_ids=frozenset({PRIMARY_ADMIN_ID}))
        ensure_admin_roles(session,settings)

        owner_ctx=_context(session,1898025825)
        owner_update=owner_ctx
        asyncio.run(admin_v2._roles_manage_screen(owner_update,owner_ctx))
        assert "إدارة الأدمنات" in owner_update.callback_query.edit_message_text.await_args.args[0]

        employee_ctx=_context(session,1923538306)
        employee_update=employee_ctx
        result=asyncio.run(admin_v2._roles_manage_screen(employee_update,employee_ctx))
        assert result == admin_v2.END
        employee_update.callback_query.answer.assert_awaited_once()


def test_employee_ids_are_not_admin_by_static_legacy_list_but_are_admin_via_effective_role():
    from app.services.admin_access import effective_role
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        settings=SimpleNamespace(admin_access=None, admin_user_ids=frozenset({PRIMARY_ADMIN_ID}))
        ensure_admin_roles(session,settings)
        assert effective_role(SimpleNamespace(application=SimpleNamespace(bot_data={"session_factory": lambda: session, "settings": settings})), 1923538306) == "manager"
