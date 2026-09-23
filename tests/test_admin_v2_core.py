import json
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.admin_models import AdminBackup, AdminAuditLog, AdminSetting, OrderAdminMeta, ProfileAdminMeta
from app.database.models import Base, Profile, ProfileContact
from app.services.admin_access import AdminRole, build_admin_access
from app.services.admin_meta import build_snapshot, backfill_meta, create_backup, get_setting, log_admin_action, payment_method, restore_snapshot, service_price, set_setting
from app.services.duplicates import find_profile_duplicates
from app.services.profile_quality import score_profile
from app.services.profiles import ProfileDraft


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _draft(name="آية", phone="0933111111"):
    return ProfileDraft(
        public_data={"gender": "female", "name": name, "age": 25, "residence": "دمشق", "marital_status": "عزباء", "children_count": 0, "occupation": "مدرسة", "education": "جامعي", "height": 165.0, "weight": 58.0, "appearance": "جذابة", "partner_requirements": "جاد بالزواج", "photo_file_id": "photo"},
        private_contact_data={"phone": phone, "whatsapp": phone, "telegram_username": None},
    )


def test_legacy_admin_ids_remain_owner_and_explicit_roles_work():
    access = build_admin_access("123", "", "456", "789")
    assert access.role_for(123) == AdminRole.OWNER
    assert access.role_for(456) == AdminRole.MANAGER
    assert access.role_for(789) == AdminRole.VIEWER
    assert access.role_for(999) is None


def test_quality_score_is_actionable():
    report = score_profile(_draft())
    assert report.score >= 75
    assert report.ready is True


def test_metadata_backfill_preserves_existing_rows():
    engine = _db()
    with Session(engine) as session:
        profile = Profile(gender="female", name="آية", age=25, residence="دمشق", status="active")
        session.add(profile)
        session.flush()
        session.add(ProfileContact(profile_id=profile.id, phone="0933111111"))
        session.commit()
        backfill_meta(session)
        assert session.get(Profile, profile.id).name == "آية"
        assert session.get(ProfileContact, profile.id).phone == "0933111111"
        assert session.get(ProfileAdminMeta, profile.id) is not None


def test_backup_and_restore_preserve_profiles_orders_and_settings():
    engine = _db()
    with Session(engine) as session:
        profile = Profile(gender="female", name="آية", age=25, residence="دمشق", status="active")
        session.add(profile); session.flush()
        session.add(ProfileContact(profile_id=profile.id, whatsapp="0933111111"))
        session.add(ProfileAdminMeta(profile_id=profile.id, quality_score=88, publication_status="published"))
        session.add(AdminSetting(key="service_amount_usd", value="7.00"))
        session.commit()

        backup = create_backup(session, 123, "اختبار")
        session.commit()
        snapshot = build_snapshot(session)

        session.execute(ProfileAdminMeta.__table__.delete())
        session.execute(ProfileContact.__table__.delete())
        session.execute(Profile.__table__.delete())
        session.commit()

        result = restore_snapshot(session, backup.snapshot_json)
        session.commit()
        assert result["profiles"] == 1
        assert session.query(Profile).count() == 1
        assert session.query(ProfileContact).count() == 1
        assert get_setting(session, "service_amount_usd", "5.00") == "7.00"
        assert service_price(session) == Decimal("7.00")
        assert snapshot["profiles"][0]["name"] == "آية"


def test_audit_and_settings_are_persistent():
    engine = _db()
    with Session(engine) as session:
        set_setting(session, "payment_method", "شام كاش", 123)
        log_admin_action(session, 123, "profile_add", "profile", 101, {"quality": 90})
        session.commit()
        assert payment_method(session) == "شام كاش"
        assert session.query(AdminAuditLog).count() == 1


def test_duplicate_detection_finds_matching_contact():
    engine = _db()
    with Session(engine) as session:
        profile = Profile(gender="female", name="آية أحمد", age=25, residence="دمشق", status="active")
        session.add(profile); session.flush()
        session.add(ProfileContact(profile_id=profile.id, phone="0933111111"))
        session.commit()
        matches = find_profile_duplicates(session, _draft(name="آية أحمد", phone="0933111111"))
        assert matches
        assert matches[0].score >= 100


def test_primary_and_default_staff_roles_are_seeded_once_and_removal_persists():
    from app.services.admin_meta import ensure_admin_roles, get_admin_roles, save_admin_roles, PRIMARY_ADMIN_ID, DEFAULT_MANAGER_IDS

    engine = _db()
    class Settings:
        admin_access = None
        admin_user_ids = frozenset({PRIMARY_ADMIN_ID})

    with Session(engine) as session:
        roles = ensure_admin_roles(session, Settings())
        assert roles[PRIMARY_ADMIN_ID] == "owner"
        assert all(roles[uid] == "manager" for uid in DEFAULT_MANAGER_IDS)

        roles = get_admin_roles(session, Settings())
        removed = next(iter(DEFAULT_MANAGER_IDS))
        roles.pop(removed)
        save_admin_roles(session, roles, PRIMARY_ADMIN_ID)
        session.commit()

        ensure_admin_roles(session, Settings())
        persisted = get_admin_roles(session, Settings())
        assert removed not in persisted
        assert persisted[PRIMARY_ADMIN_ID] == "owner"


def test_owner_can_add_and_remove_employee_and_notify_remaining_admins():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.handlers import admin_v2

    engine = _db()
    with Session(engine) as session:
        class Settings:
            admin_user_ids = frozenset({123})
            admin_access = SimpleNamespace(
                owner_ids=frozenset({123}),
                manager_ids=frozenset(),
                viewer_ids=frozenset(),
                legacy_ids=frozenset(),
            )

        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(
            user_data={},
            application=SimpleNamespace(
                bot_data={"session_factory": lambda: Session(engine), "settings": Settings()},
                bot=bot,
            ),
        )

        def update():
            return SimpleNamespace(
                effective_user=SimpleNamespace(id=123),
                effective_message=SimpleNamespace(reply_text=AsyncMock()),
                callback_query=SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock()),
            )

        from unittest.mock import patch
        with patch.object(admin_v2, "_require_role", return_value=True), patch.object(admin_v2, "_role", return_value="owner"):
            added = update()
            asyncio.run(admin_v2._admin_role_add_execute(added, context, "1923538306"))
        from app.services.admin_meta import get_admin_roles
        with Session(engine) as check:
            roles = get_admin_roles(check, Settings())
        assert roles[1923538306] == "manager"
        assert bot.send_message.await_count == 3
        bot.send_message.reset_mock()

        with patch.object(admin_v2, "_require_role", return_value=True), patch.object(admin_v2, "_role", return_value="owner"):
            removed = update()
            asyncio.run(admin_v2._admin_role_remove_execute(removed, context, "1923538306"))
        with Session(engine) as check:
            roles = get_admin_roles(check, Settings())
        assert 1923538306 not in roles
        assert context.user_data == {}


def test_production_admin_ids_have_expected_roles():
    from app.services.admin_meta import DEFAULT_MANAGER_IDS, PRIMARY_ADMIN_ID, ensure_admin_roles, get_admin_roles

    engine = _db()
    settings = type(
        "Settings",
        (),
        {
            "admin_user_ids": frozenset({PRIMARY_ADMIN_ID, *DEFAULT_MANAGER_IDS}),
            "admin_access": None,
        },
    )()
    with Session(engine) as session:
        ensure_admin_roles(session, settings)
        roles = get_admin_roles(session, settings)
        assert PRIMARY_ADMIN_ID == 1898025825
        assert DEFAULT_MANAGER_IDS == frozenset({1923538306, 7824433847})
        assert roles[1898025825] == "owner"
        assert roles[1923538306] == "manager"
        assert roles[7824433847] == "manager"


def test_primary_admin_and_initial_staff_roles_are_seeded():
    from app.services.admin_meta import ensure_admin_roles, PRIMARY_ADMIN_ID, DEFAULT_MANAGER_IDS, get_admin_roles

    engine = _db()
    settings = type(
        "Settings",
        (),
        {
            "admin_user_ids": frozenset({PRIMARY_ADMIN_ID, *DEFAULT_MANAGER_IDS}),
            "admin_access": None,
        },
    )()
    with Session(engine) as session:
        ensure_admin_roles(session, settings)
        roles = get_admin_roles(session, settings)
        assert roles[PRIMARY_ADMIN_ID] == "owner"
        for uid in DEFAULT_MANAGER_IDS:
            assert roles[uid] == "manager"


def test_staff_removal_is_persistent_and_primary_owner_is_pinned():
    from app.services.admin_meta import get_admin_roles, save_admin_roles, PRIMARY_ADMIN_ID, DEFAULT_MANAGER_IDS

    engine = _db()
    settings = type(
        "Settings",
        (),
        {
            "admin_user_ids": frozenset({PRIMARY_ADMIN_ID, *DEFAULT_MANAGER_IDS}),
            "admin_access": None,
        },
    )()
    with Session(engine) as session:
        roles = {
            PRIMARY_ADMIN_ID: "owner",
            1923538306: "manager",
            7824433847: "manager",
        }
        save_admin_roles(session, roles, PRIMARY_ADMIN_ID)
        session.commit()
        roles.pop(1923538306)
        save_admin_roles(session, roles, PRIMARY_ADMIN_ID)
        session.commit()
        saved = get_admin_roles(session, settings)
        assert 1923538306 not in saved
        assert saved[7824433847] == "manager"
        assert saved[PRIMARY_ADMIN_ID] == "owner"


def test_staff_broadcast_targets_managers_and_confirms_primary_owner():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.handlers.admin_entry import _send_staff_notification

    engine = _db()
    settings = SimpleNamespace(
        admin_user_ids=frozenset({1898025825, 1923538306, 7824433847}),
        admin_access=SimpleNamespace(
            owner_ids=frozenset({1898025825}),
            manager_ids=frozenset({1923538306, 7824433847}),
            viewer_ids=frozenset({555555555}),
            legacy_ids=frozenset(),
        ),
    )
    sent = []

    async def fake_send_message(chat_id, text):
        sent.append((chat_id, text))

    async def fake_reply_text(text, **kwargs):
        return None

    context = SimpleNamespace(
        user_data={"v2_flow": "admin_staff_notify"},
        application=SimpleNamespace(
            bot_data={"session_factory": lambda: Session(engine), "settings": settings},
            bot=SimpleNamespace(send_message=fake_send_message),
        ),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1898025825),
        effective_message=SimpleNamespace(reply_text=fake_reply_text, text=""),
    )

    class DirectSessionFactory:
        def __call__(self):
            return Session(engine)

    context.application.bot_data["session_factory"] = DirectSessionFactory()

    asyncio.run(_send_staff_notification(update, context, "اجتماع اليوم الساعة 6"))

    ids = [chat_id for chat_id, _ in sent]
    assert 1923538306 in ids
    assert 7824433847 in ids
    assert 555555555 in ids
    assert 1898025825 in ids  # dedicated owner delivery report
    owner_messages = [text for chat_id, text in sent if chat_id == 1898025825]
    assert any("تأكيد إرسال إشعار" in text for text in owner_messages)

  
def test_staff_notification_delivers_to_all_other_admins_and_pushes_owner_confirmation():
    import asyncio
    from types import SimpleNamespace

    from app.handlers.admin_entry import _send_staff_notification

    engine = _db()
    settings = SimpleNamespace(
        admin_user_ids=frozenset({1898025825, 1923538306, 7824433847}),
        admin_access=SimpleNamespace(
            owner_ids=frozenset({1898025825}),
            manager_ids=frozenset({1923538306, 7824433847}),
            viewer_ids=frozenset({987654321}),
            legacy_ids=frozenset(),
        ),
    )
    sent = []

    async def fake_send_message(chat_id, text):
        sent.append((chat_id, text))

    async def fake_reply_text(text, **kwargs):
        return None

    context = SimpleNamespace(
        user_data={"v2_flow": "admin_staff_notify"},
        application=SimpleNamespace(
            bot_data={"session_factory": lambda: Session(engine), "settings": settings},
            bot=SimpleNamespace(send_message=fake_send_message),
        ),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1898025825),
        effective_message=SimpleNamespace(reply_text=fake_reply_text, text=""),
    )

    asyncio.run(_send_staff_notification(update, context, "اجتماع الموظفين اليوم الساعة 6"))

    ids = [chat_id for chat_id, _ in sent]
    assert 1923538306 in ids
    assert 7824433847 in ids
    assert 987654321 in ids
    assert 1898025825 in ids

    admin_messages = [
        text for chat_id, text in sent
        if chat_id in {1923538306, 7824433847, 987654321}
    ]
    assert len(admin_messages) == 3
    assert all("اجتماع الموظفين اليوم الساعة 6" in text for text in admin_messages)

    owner_messages = [text for chat_id, text in sent if chat_id == 1898025825]
    assert len(owner_messages) == 1
    assert "تأكيد إرسال إشعار" in owner_messages[0]
    assert "✅ تم التسليم: 3" in owner_messages[0]
    assert "❌ فشل الإرسال: 0" in owner_messages[0]


def test_backup_restore_handles_incomplete_profile_without_crashing():
    from app.services.admin_meta import build_snapshot, restore_snapshot

    engine = _db()
    with Session(engine) as session:
        profile = Profile(gender="female", name="سارة", age=None, residence=None, status="active")
        session.add(profile)
        session.flush()
        session.add(ProfileAdminMeta(profile_id=profile.id, publication_status="review"))
        session.commit()

        snapshot = build_snapshot(session)
        session.query(ProfileAdminMeta).delete()
        session.query(Profile).delete()
        session.commit()

        result = restore_snapshot(session, json.dumps(snapshot, ensure_ascii=False))
        session.commit()

        restored = session.query(Profile).one()
        assert result["profiles"] == 1
        assert restored.name == "سارة"
        assert restored.age is None
        assert restored.residence is None
