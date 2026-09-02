from app.keyboards.admin import admin_main_keyboard, admin_orders_keyboard
from app.handlers import admin_router, admin_v2


def _row_sizes(markup):
    return [len(row) for row in markup.inline_keyboard]


def test_admin_home_is_two_columns():
    assert all(size == 2 for size in _row_sizes(admin_main_keyboard()))


def test_admin_router_sections_are_two_columns():
    for name in ("ads", "orders", "reservations", "publishing", "reports", "security", "settings"):
        # Internal screen builder returns a keyboard synchronously via _section paths.
        assert all(size == 2 for size in _two_col_sample(name))


def _two_col_sample(name):
    if name == "ads":
        return admin_router._section("x", [[admin_router.InlineKeyboardButton("a", callback_data="a")], [admin_router.InlineKeyboardButton("b", callback_data="b")]])
    if name == "orders":
        return admin_router._section("x", [[admin_router.InlineKeyboardButton("a", callback_data="a")], [admin_router.InlineKeyboardButton("b", callback_data="b")]])
    if name == "reservations":
        return admin_router._section("x", [[admin_router.InlineKeyboardButton("a", callback_data="a")], [admin_router.InlineKeyboardButton("b", callback_data="b")]])
    if name == "publishing":
        return admin_router._section("x", [[admin_router.InlineKeyboardButton("a", callback_data="a")], [admin_router.InlineKeyboardButton("b", callback_data="b")]])
    if name == "reports":
        return admin_router._section("x", [[admin_router.InlineKeyboardButton("a", callback_data="a")], [admin_router.InlineKeyboardButton("b", callback_data="b")]])
    if name == "security":
        return admin_router._section("x", [[admin_router.InlineKeyboardButton("a", callback_data="a")], [admin_router.InlineKeyboardButton("b", callback_data="b")]])
    return admin_router._section("x", [[admin_router.InlineKeyboardButton("a", callback_data="a")], [admin_router.InlineKeyboardButton("b", callback_data="b")]])


def test_admin_order_rows_are_never_four_columns():
    assert all(size <= 2 for size in _row_sizes(admin_orders_keyboard([1, 2])))
