import app.main  # noqa: F401 - applies the admin keyboard layout policy

from app.handlers import admin_router, admin_router_legacy, admin_v2
from app.keyboards.admin import admin_main_keyboard


def _row_sizes(markup):
    return [len(row) for row in markup.inline_keyboard]


def test_admin_home_is_exactly_two_columns():
    markup = admin_main_keyboard()
    assert markup.inline_keyboard
    assert all(size == 2 for size in _row_sizes(markup))


def test_admin_router_section_is_exactly_two_columns():
    markup = admin_router._section(
        "x",
        [
            [admin_router.InlineKeyboardButton("a", callback_data="a")],
            [admin_router.InlineKeyboardButton("b", callback_data="b")],
            [admin_router.InlineKeyboardButton("c", callback_data="c")],
        ],
    )
    assert all(size == 2 for size in _row_sizes(markup))


def test_admin_v2_keyboards_are_exactly_two_columns():
    markups = [
        admin_v2._dashboard_keyboard(),
        admin_v2._profile_list_keyboard([], 0, "all", False),
        admin_v2._profile_actions(154, "active", "review"),
        admin_v2._edit_fields_keyboard(154),
    ]
    assert all(markup.inline_keyboard for markup in markups)
    assert all(
        all(size == 2 for size in _row_sizes(markup))
        for markup in markups
    )


def test_legacy_admin_keyboards_are_exactly_two_columns():
    markup = admin_router_legacy._archive_keyboard(154)
    assert all(size == 2 for size in _row_sizes(markup))
