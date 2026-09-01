from app.services.search import parse_search_text


def test_syrian_search_understands_al_prefixed_age_range_without_inventing_city_filter():
    filters = parse_search_text("بنت دمشق عمرا بين ال20 و39")

    assert filters.gender == "female"
    assert filters.province == "دمشق"
    assert filters.age_min == 20
    assert filters.age_max == 39
    assert filters.city is None
