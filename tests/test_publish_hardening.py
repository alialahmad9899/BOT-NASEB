import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.database.repositories import ProfileRepository
from app.handlers import admin_v2
from app.services.profiles import ProfileDraft


def test_publish_requires_profile_completeness(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ProfileRepository(session).create(
            ProfileDraft(
                public_data={
                    "gender": "female",
                    "name": "آية",
                    "age": None,
                    "residence": None,
                    "marital_status": None,
                },
                private_contact_data={},
            ),
            request_number=200,
        )
        session.commit()

        query = SimpleNamespace(
            data="admin:v2:publish:200",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123),
            effective_message=SimpleNamespace(),
            callback_query=query,
        )
        context = SimpleNamespace(
            user_data={},
            application=SimpleNamespace(
                bot_data={
                    "session_factory": lambda: Session(engine),
                    "settings": SimpleNamespace(
                        admin_user_ids=frozenset({123}),
                        admin_access=SimpleNamespace(role_for=lambda uid: "owner"),
                    ),
                }
            ),
        )

        monkeypatch.setattr(admin_v2, "_dashboard_keyboard", lambda: None)
        monkeypatch.setattr(admin_v2, "_require_role", lambda update, context, roles: True)
        monkeypatch.setattr(admin_v2, "_is_admin", lambda update, context: True)
        result = asyncio.run(admin_v2.admin_callback(update, context))

        assert result == admin_v2.END
        assert "ما فينا ننشر" in query.edit_message_text.await_args.args[0]
        assert "admin:v2:edit:200" in str(query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard)

