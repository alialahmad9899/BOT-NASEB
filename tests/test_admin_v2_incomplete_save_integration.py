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


def test_save_add_persists_incomplete_draft_end_to_end(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope(_context):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(admin_v2, "_session", session_scope)

    edited_messages = []

    class Callback:
        data = "admin:v2:add:save:force"

        async def edit_message_text(self, *args, **kwargs):
            edited_messages.append((args, kwargs))

    update = SimpleNamespace(
        callback_query=Callback(),
        effective_user=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(),
    )
    draft = ProfileDraft(
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
    )
    context = SimpleNamespace(
        user_data={"v2_draft": draft, "v2_pending_number": 999},
    )

    result = asyncio.run(_save_add(update, context))

    assert result == admin_v2.END
    assert edited_messages
    assert "تم حفظ الإعلان بنجاح" in edited_messages[-1][0][0]
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


def test_original_pending_number_is_ignored_when_saving(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope(_context):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(admin_v2, "_session", session_scope)

    class Callback:
        data = "admin:v2:add:save:force"

        async def edit_message_text(self, *args, **kwargs):
            pass

    draft = ProfileDraft(
        public_data={"gender": "female", "name": "آية", "age": 25, "residence": "دمشق"},
        private_contact_data={"phone": None, "telegram_username": None, "whatsapp": None},
    )
    update = SimpleNamespace(callback_query=Callback(), effective_user=SimpleNamespace(id=123), effective_message=SimpleNamespace())
    context = SimpleNamespace(user_data={"v2_draft": draft, "v2_pending_number": 145000})

    asyncio.run(_save_add(update, context))

    with Session(engine) as session:
        profile = session.query(Profile).one()
        assert profile.request_number != 145000
        assert profile.request_number == 101
