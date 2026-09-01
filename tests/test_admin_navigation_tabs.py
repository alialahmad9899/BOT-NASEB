from app.handlers import admin_router


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_admin_home_is_compact_and_grouped():
    callbacks = _callbacks(admin_router._home_keyboard())
    assert len(callbacks) == 8
    assert callbacks == [
        "admin:v2:section:ads",
        "admin:v2:add",
        "admin:v2:section:orders",
        "admin:v2:section:reservations",
        "admin:v2:section:publishing",
        "admin:v2:section:reports",
        "admin:v2:section:security",
        "admin:v2:section:settings",
    ]


def test_admin_ads_menu_is_nested():
    callbacks = _callbacks(admin_router._section("x", [[ ]]))
    assert callbacks[-1] == "admin:v2:dashboard"


def test_admin_group_callbacks_are_distinct():
    callbacks = {
        "ads": "admin:v2:section:ads",
        "orders": "admin:v2:section:orders",
        "reservations": "admin:v2:section:reservations",
        "publishing": "admin:v2:section:publishing",
        "reports": "admin:v2:section:reports",
        "security": "admin:v2:section:security",
        "settings": "admin:v2:section:settings",
    }
    assert len(set(callbacks.values())) == len(callbacks)
