from app.keyboards.client import client_search_confirm_keyboard


def test_search_confirmation_keyboard_has_execute_edit_and_home():
    callbacks = [
        button.callback_data
        for row in client_search_confirm_keyboard().inline_keyboard
        for button in row
    ]
    assert "client:search:execute" in callbacks
    assert "client:search:edit" in callbacks
    assert "client:menu" in callbacks
