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
