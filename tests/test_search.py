from app.services.ai import SearchFilterExtraction
from app.services.search import filters_from_ai, parse_search_text


def test_syrian_search_understands_age_range_and_unified_residence():
    filters = parse_search_text("بنت دمشق عمرا بين ال20 و39")

    assert filters.gender == "female"
    assert filters.residence == "دمشق"
    assert filters.age_min == 20
    assert filters.age_max == 39


def test_ai_search_uses_one_residence_field():
    extraction = SearchFilterExtraction(
        gender="female",
        residence="دمشق",
        age_min=20,
        age_max=39,
    )

    filters = filters_from_ai(extraction, "بنت دمشق عمرا بين ال20 و39")

    assert filters.gender == "female"
    assert filters.residence == "دمشق"
    assert filters.age_min == 20
    assert filters.age_max == 39


def test_search_understands_sham_as_damascus():
    filters = parse_search_text("بدي بنت من الشام بين 22 و28")

    assert filters.gender == "female"
    assert filters.residence == "دمشق"
    assert filters.age_min == 22
    assert filters.age_max == 28


def test_search_understands_rural_residence_as_one_field():
    filters = parse_search_text("بدي بنت من ريف حمص عمرها 25")

    assert filters.gender == "female"
    assert filters.residence == "ريف حمص"
    assert filters.age_min == 25
    assert filters.age_max == 25


def test_ai_search_accepts_specific_residence():
    extraction = SearchFilterExtraction(
        gender="male",
        residence="ريف حماة",
        age_min=28,
        age_max=35,
    )

    filters = filters_from_ai(extraction, "بدي عريس ساكن بريف حماة بين 28 و35")

    assert filters.gender == "male"
    assert filters.residence == "ريف حماة"
    assert filters.age_min == 28
    assert filters.age_max == 35


def test_search_normalizes_marital_typo():
    extraction = SearchFilterExtraction(
        gender="female",
        residence="دمشق",
        marital_status="مطلقة",
    )

    filters = filters_from_ai(extraction, "بنت من الشام مطلقه")

    assert filters.gender == "female"
    assert filters.residence == "دمشق"
    assert filters.marital_status == "مطلقة"


def test_search_supports_children_filter():
    filters = parse_search_text("بدي عروس من حلب بدون ولاد")

    assert filters.gender == "female"
    assert filters.residence == "حلب"
    assert filters.children_min == 0
    assert filters.children_max == 0
