from app.services.ai import basic_profile_extraction


def test_real_world_syrian_marriage_text_extracts_age_and_residence_without_making_phrase_a_name():
    raw = """بنت من سوريا
عمري 20 من دمشق
بدي شب منيح ما بدخن وطويل رقمي 0948484848"""

    parsed = basic_profile_extraction(raw)

    assert parsed.gender == "female"
    assert parsed.age == 20
    assert parsed.residence == "دمشق"
    assert parsed.phone == "0948484848"
    assert parsed.name is None
    assert parsed.partner_requirements == "بدي شب منيح ما بدخن وطويل"
