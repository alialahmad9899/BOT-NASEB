from app.services.ai import ProfileExtraction
from app.services.profiles import format_client_profile, validate_profile_extraction


def test_profile_schema_uses_unified_residence_and_requested_fields():
    fields = set(ProfileExtraction.model_fields)
    assert "residence" in fields
    assert "province" not in fields
    assert "city" not in fields
    assert "nationality" not in fields
    assert "religion" not in fields
    assert "description" not in fields


def test_marriage_profile_format_matches_requested_shape():
    text = format_client_profile({
        "request_number": 139,
        "gender": "female",
        "name": "خلود",
        "age": 27,
        "residence": "ريف حماة",
        "occupation": "ربة منزل",
        "education": "شهادة بكالوريا",
        "marital_status": "عزباء",
        "children_count": None,
        "height": 158,
        "weight": 62,
        "appearance": "سمراء جذابة، محجبة",
        "partner_requirements": "العمر لا يتجاوز 40 سنة، عربي مسلم، جاد بالزواج، صادق، أمين وحنون",
        "status": "active",
    })

    assert "💍 طلب زواج (رقم الطلب: 139)" in text
    assert "📍 الإقامة: سوريا - ريف حماة" in text
    assert "📚 المستوى التعليمي: شهادة بكالوريا" in text
    assert "👤 الشكل: سمراء جذابة، محجبة" in text
    assert "💙 مواصفات الشريك المطلوب:" in text
    assert "الجنسية" not in text
    assert "الديانة" not in text
    assert "المواصفات الشخصية" not in text


def test_non_single_profile_requires_child_count():
    extraction = ProfileExtraction(
        gender="female",
        name="منا",
        age=30,
        residence="حلب",
        marital_status="مطلقة",
    )
    result = validate_profile_extraction(extraction, {"phone": "0930000000"})
    assert "children_count" in result.missing_fields
