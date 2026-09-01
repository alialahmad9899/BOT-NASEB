from app.keyboards.admin import add_preview_keyboard, confirm_disable_keyboard, profile_actions_keyboard
from app.keyboards.client import client_main_keyboard, client_results_keyboard, client_search_keyboard


def _button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callback_data(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_client_main_has_explicit_bride_and_groom_search_options():
    texts = _button_texts(client_main_keyboard())

    assert "🤵 بدي عريس" in texts
    assert "💗 بدي عروس" in texts
    assert "🤵 دورولي على عريس مناسب" not in texts
    assert "👰 دورولي على عروس مناسبة" not in texts


def test_client_search_has_main_menu_back_button():
    callbacks = _callback_data(client_search_keyboard())

    assert "client:menu" in callbacks


def test_client_results_has_main_menu_back_button():
    callbacks = _callback_data(client_results_keyboard([101]))

    assert "client:menu" in callbacks


def test_admin_add_preview_has_admin_menu_back_button():
    callbacks = _callback_data(add_preview_keyboard(can_save=False))

    assert "admin:menu" in callbacks


def test_admin_actions_have_admin_menu_back_button():
    assert "admin:menu" in _callback_data(profile_actions_keyboard(101))
    assert "admin:disable:cancel" in _callback_data(confirm_disable_keyboard(101))
