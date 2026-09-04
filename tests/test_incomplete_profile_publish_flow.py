from app.services.profiles import ProfileDraft, ProfileValidation, validate_profile_extraction
from app.services.ai import ProfileExtraction
from app.handlers.admin_entry import _publish_view_keyboard


def test_missing_profile_fields_are_warnings_not_blocking_errors():
    extraction = ProfileExtraction()
    result = validate_profile_extraction(extraction, {})

    assert result.missing_fields
    assert result.errors == ()
    assert result.ok is True


def test_publish_view_keyboard_keeps_publish_action_for_saved_profile():
    keyboard = _publish_view_keyboard(139, "review")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]

    assert "admin:v2:publish:139" in callbacks


def test_publish_view_keyboard_changes_to_unpublish_after_publication():
    keyboard = _publish_view_keyboard(139, "published")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]

    assert "admin:v2:unpublish:139" in callbacks
