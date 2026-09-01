from app.services.ai import ProfileExtraction, normalize_profile_extraction
from app.services.profiles import format_client_profile


def test_profile_schema_keeps_family_education_identity_and_contact_separate():
    extraction = normalize_profile_extraction(
        ProfileExtraction(
            gender="female",
            name="منا",
            age=30,
            province="حلب",
            city=None,
            marital_status="مطلقة",
            occupation="طالبة طب",
            education="دراسة الطب",
            nationality="عربية",
            religion="مسلمة",
            children_count=0,
            height=160,
            weight=60,
            appearance="سمراء جذابة، محجبة",
            description="بتحب الغناء وصوتها حلو.",
            partner_requirements="شاب طويل وغير مدخن.",
            phone="0934888392",
        )
    )

    assert extraction.children_count == 0
    assert extraction.education == "دراسة الطب"
    assert extraction.nationality == "عربية"
    assert extraction.religion == "مسلمة"
    assert extraction.appearance == "سمراء جذابة، محجبة"
    assert extraction.city == "حلب"
    assert extraction.phone == "0934888392"


def test_client_profile_uses_marriage_post_style_and_never_exposes_phone():
    profile = {
        "request_number": 139,
        "gender": "female",
        "name": "خلود",
        "age": 27,
        "province": "ريف حماة",
        "city": None,
        "marital_status": "عزباء",
        "occupation": "ربة منزل",
        "education": "شهادة بكالوريا",
        "nationality": "عربية",
        "religion": "مسلمة",
        "children_count": None,
        "height": 158,
        "weight": 62,
        "appearance": "سمراء جذابة، محجبة",
        "description": "",
        "partner_requirements": "عمره لا يتجاوز 40 سنة، عربي مسلم، جاد بالزواج، صادق، أمين، حنون.",
        "phone": "0900000000",
        "status": "active",
    }

    rendered = format_client_profile(profile)

    assert "طلب زواج (رقم الطلب: 139)" in rendered
    assert "المستوى التعليمي: شهادة بكالوريا" in rendered
    assert "الجنسية والديانة: عربية، مسلمة" in rendered
    assert "الشكل: سمراء جذابة، محجبة" in rendered
    assert "المواصفات الشخصية:" in rendered
    assert "مواصفات الشريك المطلوب:" in rendered
    assert "0900000000" not in rendered
