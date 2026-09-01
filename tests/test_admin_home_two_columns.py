from app.keyboards.admin import admin_main_keyboard


def test_admin_home_uses_two_columns():
    rows = admin_main_keyboard().inline_keyboard
    assert len(rows) == 4
    assert all(len(row) == 2 for row in rows)
    assert [button.callback_data for row in rows for button in row] == [
        "admin:v2:section:ads",
        "admin:v2:add",
        "admin:v2:section:orders",
        "admin:v2:section:reservations",
        "admin:v2:section:publishing",
        "admin:v2:section:reports",
        "admin:v2:section:security",
        "admin:v2:section:settings",
    ]
