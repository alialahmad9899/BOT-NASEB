from app.services.profiles import ProfileDraft, ProfileValidation, validate_profile_extraction
from app.services.ai import ProfileExtraction
from app.handlers.admin_entry import _publish_view_keyboard
from app.database.models import Base
from app.database.repositories import ProfileRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_missing_profile_fields_are_warnings_not_blocking_errors():
    extraction = ProfileExtraction()
    result = validate_profile_extraction(extraction, {})

    assert result.missing_fields
    assert result.errors == ()
    assert result.ok is True


def test_incomplete_profile_can_be_persisted_without_inventing_values():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    draft = ProfileDraft(
        public_data={
            "gender": None,
            "name": "آية",
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

    with Session(engine) as session:
        profile = ProfileRepository(session).create(draft, request_number=139)
        session.commit()
        saved = ProfileRepository(session).get_public(profile.request_number)

    assert saved["name"] == "آية"
    assert saved["age"] is None
    assert saved["residence"] is None
    assert saved["gender"] is None


def test_publish_view_keyboard_keeps_publish_action_for_saved_profile():
    keyboard = _publish_view_keyboard(139, "review")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]

    assert "admin:v2:publish:139" in callbacks


def test_publish_view_keyboard_changes_to_unpublish_after_publication():
    keyboard = _publish_view_keyboard(139, "published")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]

    assert "admin:v2:unpublish:139" in callbacks
