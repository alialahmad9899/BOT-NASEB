from app.services.ai import SearchFilterExtraction
from app.services.search import filters_from_ai, parse_search_text


def test_syrian_search_understands_al_prefixed_age_range_without_inventing_city_filter():
    filters = parse_search_text("بنت دمشق عمرا بين ال20 و39")

    assert filters.gender == "female"
    assert filters.province == "دمشق"
    assert filters.age_min == 20
    assert filters.age_max == 39
    assert filters.city is None


def test_ai_search_filters_do_not_add_same_province_as_city_without_explicit_city_reference():
    extraction = SearchFilterExtraction(
        gender="female",
        province="دمشق",
        city="دمشق",
        age_min=20,
        age_max=39,
    )

    filters = filters_from_ai(extraction, "بنت دمشق عمرا بين ال20 و39")

    assert filters.province == "دمشق"
    assert filters.city is None
    assert filters.age_min == 20
    assert filters.age_max == 39
