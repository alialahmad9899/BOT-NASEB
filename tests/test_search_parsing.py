from app.services.search import parse_search_text


def test_search_parser_understands_syrian_arabic_age_range_and_gender():
    result = parse_search_text("بدي بنت من دمشق بين ٢٢ و٢٧ سنة")
    assert result.gender == "female"
    assert result.province == "دمشق"
    assert result.age_min == 22
    assert result.age_max == 27


def test_search_parser_understands_marital_status_and_city():
    result = parse_search_text("عزباء من جرمانا")
    assert result.marital_status == "عزباء"
    assert result.city == "جرمانا"


def test_search_parser_does_not_treat_users_own_age_as_target_age():
    result = parse_search_text("عمري 30 وبدي بنت من دمشق")
    assert result.gender == "female"
    assert result.province == "دمشق"
    assert result.age_min is None
    assert result.age_max is None


def test_search_parser_recognizes_standalone_target_age():
    result = parse_search_text("عمر 26 من دمشق")
    assert result.age_min == 26
    assert result.age_max == 26


def test_search_parser_does_not_use_users_own_age_as_target_when_ai_can_help_later():
    result = parse_search_text("عمري ٣٠ ساكن دمشق وبدي عروس")
    assert result.age_min is None
    assert result.age_max is None


def test_ai_filter_sanitizer_rejects_users_own_age_as_target():
    from app.services.ai import SearchFilterExtraction
    from app.services.search import filters_from_ai

    result = filters_from_ai(
        SearchFilterExtraction(age_min=30, province="دمشق"),
        "عمري 30 وبدي عروس من دمشق",
    )
    assert result.age_min is None
    assert result.province == "دمشق"


def test_ai_filter_sanitizer_keeps_explicit_target_age():
    from app.services.ai import SearchFilterExtraction
    from app.services.search import filters_from_ai

    result = filters_from_ai(
        SearchFilterExtraction(age_min=22, age_max=27, province="دمشق"),
        "بدي بنت من دمشق بين 22 و27",
    )
    assert result.age_min == 22
    assert result.age_max == 27
