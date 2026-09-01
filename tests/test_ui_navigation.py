from app.keyboards.client import client_main_keyboard, client_profile_keyboard, client_results_keyboard, client_search_keyboard


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_client_main_offers_gender_specific_match_actions():
    labels = _labels(client_main_keyboard())
    assert "🤵 بدي عريس" in labels
    assert "💗 بدي عروس" in labels
    assert "🤵 دورولي على عريس مناسب" not in labels
    assert "👰 دورولي على عروس مناسبة" not in labels
    assert "💗 دورولي على شريك مناسب" not in labels


def test_client_search_and_results_have_main_menu_navigation():
    assert "⬅️ القائمة الرئيسية" in _labels(client_search_keyboard())
    assert "🏠 الرئيسية" not in _labels(client_search_keyboard())
    assert "🏠 الرئيسية" in _labels(client_results_keyboard([101]))
    assert "🏠 الرئيسية" in _labels(client_profile_keyboard(101))


def test_reserved_profile_hides_contact_request():
    labels = _labels(client_profile_keyboard(101, "reserved"))
    assert "🔒 العرض محجوز حالياً" in labels
    assert "📩 أطلب التواصل" not in labels
