import pytest

from app.services.ai import AIService, ProfileExtraction, SearchFilterExtraction, basic_profile_extraction, merge_private_contacts, normalize_profile_extraction
from app.services.profiles import validate_profile_extraction


def test_profile_extraction_validation_reports_missing_required_data():
    extraction = ProfileExtraction(name="آية", age=24, residence=None, gender="female")
    result = validate_profile_extraction(extraction, {"phone": "0900000000"})
    assert "residence" in result.missing_fields


def test_profile_extraction_does_not_invent_contact_data():
    extraction = ProfileExtraction(name="آية", age=24, residence="دمشق", gender="female")
    result = validate_profile_extraction(extraction, {})
    assert "contact" in result.missing_fields


def test_ai_service_without_key_is_not_configured():
    service = AIService(None)
    assert service.is_configured is False
    with pytest.raises(RuntimeError):
        service.extract_profile_sync("آية 24 دمشق")


def test_search_filter_extraction_accepts_age_range():
    parsed = SearchFilterExtraction(age_min=22, age_max=27, residence="دمشق")
    assert parsed.age_min == 22
    assert parsed.age_max == 27
    assert parsed.residence == "دمشق"


def test_basic_profile_fallback_extracts_arabic_digits_without_inventing_missing_data():
    parsed = basic_profile_extraction("آية\n٢٤ سنة\nأنثى\nريف دمشق\nجرمانا\nمدرسة\n09xxxxxxxx")
    assert parsed.name == "آية"
    assert parsed.age == 24
    assert parsed.gender == "female"
    assert parsed.residence is not None
    assert "جرمانا" in parsed.residence or parsed.residence == "ريف دمشق"
    assert parsed.occupation == "مدرسة"
    assert parsed.phone == "09xxxxxxxx"


def test_basic_profile_fallback_keeps_unknown_fields_null():
    parsed = basic_profile_extraction("آية\n٢٤ سنة")
    assert parsed.age == 24
    assert parsed.residence is None
    assert parsed.phone is None


def test_basic_profile_fallback_extracts_damascus_residence():
    parsed = basic_profile_extraction("اسمي آية\nعمري 25 من دمشق\nعزباء\nمدرسة\n09xxxxxxxx")
    assert parsed.residence == "دمشق"


def test_normalize_profile_extraction_keeps_unified_residence():
    extraction = ProfileExtraction(gender="female", residence=" دمشق ")
    normalized = normalize_profile_extraction(extraction)
    assert normalized.residence == "دمشق"


def test_ai_output_is_normalized_before_validation():
    extraction = ProfileExtraction(gender="أنثى", residence=" دمشق ", phone="٠٩١١٢٢٣٣٤٤")
    normalized = normalize_profile_extraction(extraction)
    assert normalized.gender == "female"
    assert normalized.residence == "دمشق"
    assert normalized.phone == "0911223344"


def test_ai_private_contacts_are_replaced_by_deterministic_values():
    ai_result = ProfileExtraction(phone="0000000000", telegram_username="invented")
    deterministic = ProfileExtraction(phone="0911223344", telegram_username="real_user")
    merged = merge_private_contacts(ai_result, deterministic)
    assert merged.phone == "0911223344"
    assert merged.telegram_username == "real_user"


def test_ai_private_contacts_are_cleared_when_not_explicitly_found():
    ai_result = ProfileExtraction(phone="0000000000", telegram_username="invented")
    deterministic = ProfileExtraction()
    merged = merge_private_contacts(ai_result, deterministic)
    assert merged.phone is None
    assert merged.telegram_username is None
