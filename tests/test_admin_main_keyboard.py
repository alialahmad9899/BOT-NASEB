from app.keyboards.admin import admin_main_keyboard


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_admin_main_keyboard_uses_compact_grouped_navigation():
    assert _callbacks(admin_main_keyboard()) == [
        "admin:v2:section:ads",
        "admin:v2:add",
        "admin:v2:section:orders",
        "admin:v2:section:reservations",
        "admin:v2:section:publishing",
        "admin:v2:section:reports",
        "admin:v2:section:security",
        "admin:v2:section:settings",
    ]
