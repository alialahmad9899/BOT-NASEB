from app.services.payment import normalize_whatsapp


def test_normalize_syrian_local_whatsapp():
    assert normalize_whatsapp("09 348 883 92") == "+963934888392"


def test_normalize_syrian_international_whatsapp():
    assert normalize_whatsapp("+963 934 888 392") == "+963934888392"


def test_normalize_syrian_00_prefix_whatsapp():
    assert normalize_whatsapp("00963 934 888 392") == "+963934888392"


def test_reject_invalid_whatsapp():
    assert normalize_whatsapp("12345") is None
