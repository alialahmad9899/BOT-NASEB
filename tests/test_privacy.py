from app.services.profiles import ProfileDraft, apply_text_edits, format_admin_profile, format_client_profile


def profile_fixture():
    return {
        "request_number": 154,
        "name": "آية",
        "gender": "female",
        "age": 24,
        "residence": "ريف دمشق - جرمانا",
        "marital_status": "عزباء",
        "occupation": "مدرسة",
        "education": "بكالوريا",
        "height": 165,
        "weight": None,
        "appearance": "محجبة",
        "partner_requirements": "شاب محترم",
        "phone": "0900000000",
        "telegram_username": "aya24",
        "whatsapp": "0900000000",
        "status": "active",
    }


def test_client_profile_has_no_private_contact_fields():
    text = format_client_profile(profile_fixture())
    assert "0900000000" not in text
    assert "aya24" not in text
    assert "معلومات التواصل محفوظة لدى الصفحة" in text


def test_admin_profile_contains_private_contact_fields():
    text = format_admin_profile(profile_fixture())
    assert "0900000000" in text
    assert "aya24" in text


def test_apply_text_edits_can_change_residence_and_private_fields():
    draft = ProfileDraft(
        public_data={"age": 24, "residence": "دمشق", "gender": "female"},
        private_contact_data={"phone": "0900"},
    )
    updated = apply_text_edits(draft, "العمر=25\nمكان السكن=ريف دمشق - جرمانا\nرقم الهاتف=0911")
    assert updated.public_data["age"] == 25
    assert updated.public_data["residence"] == "ريف دمشق - جرمانا"
    assert updated.private_contact_data["phone"] == "0911"
