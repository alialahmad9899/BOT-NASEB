from app.services.profiles import ProfileDraft, apply_text_edits, extraction_to_draft, validate_profile_extraction
from app.services.ai import ProfileExtraction


def test_arabic_gender_edit_is_normalized_to_database_value():
    draft = ProfileDraft(public_data={"gender": None}, private_contact_data={})
    edited = apply_text_edits(draft, "النوع=أنثى")
    assert edited.public_data["gender"] == "female"


def test_arabic_gender_from_extraction_is_normalized_before_persistence():
    draft = extraction_to_draft(ProfileExtraction(gender="أنثى"))
    assert draft.public_data["gender"] == "female"


def test_invalid_gender_is_a_blocking_validation_error_but_missing_gender_is_not():
    missing = validate_profile_extraction(ProfileExtraction(), {})
    invalid = validate_profile_extraction(ProfileExtraction(gender="unknown"), {})

    assert missing.ok is True
    assert "gender" in missing.missing_fields
    assert invalid.ok is False
    assert invalid.errors
