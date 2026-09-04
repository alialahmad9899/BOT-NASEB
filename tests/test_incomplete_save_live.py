import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.admin_models import AdminAuditLog, ProfileAdminMeta
from app.database.models import Base, Profile, ProfileContact
from app.handlers import admin_v2
from app.handlers.incomplete_save_override import _save_add
from app.services.profiles import ProfileDraft


def test_hardened_save_persists_incomplete_profile_and_uses_fresh_number(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope(_context):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(admin_v2, "_session", session_scope)

    class Callback:
        async def edit_message_text(self, *args, **kwargs):
            self.last_message = args[0]

    callback = Callback()
    update = SimpleNamespace(
        callback_query=callback,
        effective_user=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(),
    )
    context = SimpleNamespace(
        user_data={
            "v2_pending_number": 999999,
            "v2_draft": ProfileDraft(
                public_data={
                    "gender": "female",
                    "name": None,
                    "age": None,
                    "residence": None,
                    "marital_status": None,
                    "children_count": None,
                    "occupation": None,
                    "education": None,
                    "height": None,
                    "weight": None,
                    "appearance": None,
                    "partner_requirements": None,
                    "photo_file_id": None,
                },
                private_contact_data={"phone": None, "telegram_username": None, "whatsapp": None},
            ),
        }
    )

    result = asyncio.run(_save_add(update, context))

    assert result == admin_v2.END
    assert "تم حفظ الإعلان بنجاح" in callback.last_message
    assert context.user_data == {}

    with Session(engine) as session:
        profile = session.query(Profile).one()
        assert profile.request_number == 101
        assert profile.gender == "female"
        assert profile.age is None
        assert profile.residence is None
        assert session.query(ProfileContact).count() == 1
        assert session.query(ProfileAdminMeta).count() == 1
        assert session.query(AdminAuditLog).count() == 1
