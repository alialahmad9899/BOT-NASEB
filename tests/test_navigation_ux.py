import inspect

from app.handlers import admin as admin_handler
from app.handlers import client as client_handler
from app.keyboards.admin import admin_main_keyboard, add_preview_keyboard
from app.keyboards.client import client_main_keyboard, client_profile_keyboard, client_results_keyboard


def _texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_client_main_exposes_simple_actions():
    texts = _texts(client_main_keyboard())
    assert "💳 طلباتي" in texts
    assert "🤵 دورولي على عريس مناسب" in texts
    assert "👰 دورولي على عروس مناسبة" in texts


def test_client_results_offer_new_search_and_home():
    callbacks = _callbacks(client_results_keyboard([101, 102]))
    assert "client:search" in callbacks
    assert "client:menu" in callbacks


def test_client_profile_offer_new_search_and_home():
    callbacks = _callbacks(client_profile_keyboard(101, "active"))
    assert "client:search" in callbacks
    assert "client:menu" in callbacks


def test_admin_delete_menu_has_explicit_delete_all_action():
    from app.keyboards.admin import admin_delete_menu_keyboard

    callbacks = _callbacks(admin_delete_menu_keyboard())
    assert "admin:delete:all" in callbacks
    assert "admin:delete:cancel" in callbacks


def test_admin_preview_always_has_an_exit_path():
    assert "admin:menu" in _callbacks(add_preview_keyboard(False))


def test_visible_callback_prefixes_are_handled():
    admin_source = inspect.getsource(admin_handler.admin_callback)
    client_source = inspect.getsource(client_handler.client_callback)
    for callback in _callbacks(admin_main_keyboard()):
        assert callback.split(":")[0] == "admin"
        assert "admin:" in admin_source or callback == "admin:menu"
    for callback in _callbacks(client_main_keyboard()):
        assert callback.split(":")[0] == "client"
        assert "client:" in client_source or callback == "client:menu"
