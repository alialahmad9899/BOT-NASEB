from app.services.ai import ProfileExtraction
from app.services.profiles import ProfileDraft, format_client_profile, format_draft_preview, mask_phone, validate_profile_extraction


def test_profile_schema_uses_unified_residence_and_requested_fields():
    fields = set(ProfileExtraction.model_fields)
    assert "residence" in fields
    assert "province" not in fields
    assert "city" not in fields
    assert "nationality" not in fields
    assert "religion" not in fields
    assert "description" not in fields


def test_marriage_profile_format_matches_requested_publishable_shape():
    text = format_client_profile({
        "request_number": 139, "name": "خلود", "gender": "female", "age": 27,
        "residence": "ريف حماة", "occupation": "ربة منزل", "education": "شهادة بكالوريا",
        "marital_status": "عزباء", "children_count": None, "height": 158, "weight": 62,
        "appearance": "سمراء جذابة، محجبة",
        "partner_requirements": "العمر: لا يتجاوز 40 سنة\nالجنسية والديانة: عربي مسلم\nالصفات: جاد بالزواج، صادق، أمين، وحنون",
        "status": "active",
    }, masked_phone="09••••••92")
    assert "💍 طلب زواج (رقم الطلب: 139)" in text
    assert "الاسم: خلود 👩" in text
    assert "العمر: 27 سنة 🎂" in text
    assert "الإقامة: سوريا - ريف حماة 📍" in text
    assert "العمل: ربة منزل 💼" in text
    assert "المستوى التعليمي: شهادة بكالوريا 📚" in text
    assert "الحالة الاجتماعية: عزباء 💍" in text
    assert "المواصفات الشخصية: 💗" in text
    assert "الطول: 158 سم" in text
    assert "الوزن: 62 كغم" in text
    assert "الشكل: سمراء جذابة، محجبة" in text
    assert "مواصفات الشريك المطلوب: 💙" in text
    assert "العمر: لا يتجاوز 40 سنة" in text
    assert "الجنسية والديانة: عربي مسلم" in text
    assert "الصفات: جاد بالزواج، صادق، أمين، وحنون" in text
    assert "09••••••92" in text
    assert "للتواصل: يُرجى المراسلة عبر الرسائل الخاصة لصفحتنا مع ذكر رقم الطلب (139)" in text
    assert "0900000092" not in text


def test_draft_preview_contains_publishable_copy_and_secret_admin_contact():
    draft = ProfileDraft(
        public_data={
            "gender": "female", "name": "خلود", "age": 27, "residence": "ريف حماة",
            "occupation": "ربة منزل", "education": "شهادة بكالوريا", "marital_status": "عزباء",
            "children_count": None, "height": 158, "weight": 62, "appearance": "سمراء جذابة، محجبة",
            "partner_requirements": "العمر: لا يتجاوز 40 سنة\nالصفات: جاد بالزواج، صادق، أمين، وحنون",
            "photo_file_id": None,
        },
        private_contact_data={"phone": "0900000092"},
    )
    text = format_draft_preview(draft, request_number=139)
    assert "💍 طلب زواج (رقم الطلب: 139)" in text
    assert "الإقامة: سوريا - ريف حماة 📍" in text
    assert "مواصفات الشريك المطلوب: 💙" in text
    assert "للتواصل: يُرجى المراسلة عبر الرسائل الخاصة لصفحتنا مع ذكر رقم الطلب (139)" in text
    assert "🔐 بيانات التواصل للأدمن فقط:\n📱 الهاتف: 0900000092" in text


def test_client_phone_is_masked_only():
    assert mask_phone("0900000092") == "09••••••92"
    assert mask_phone("0934888392") == "09••••••92"


def test_non_single_profile_requires_child_count():
    extraction = ProfileExtraction(gender="female", name="منا", age=30, residence="حلب", marital_status="مطلقة")
    result = validate_profile_extraction(extraction, {"phone": "0930000000"})
    assert "children_count" in result.missing_fields
