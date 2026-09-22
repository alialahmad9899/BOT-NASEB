import inspect

from telegram import InlineKeyboardMarkup

from app.handlers import admin_entry, admin_router_legacy, admin_v2, safe_routing
from app.keyboards.admin import admin_main_keyboard


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_single_admin_dashboard_keyboard_is_used_everywhere():
    assert isinstance(admin_v2._dashboard_keyboard(), InlineKeyboardMarkup)
    assert _callbacks(admin_v2._dashboard_keyboard()) == _callbacks(admin_main_keyboard())


def test_sensitive_v2_callbacks_require_manager_or_owner():
    manager_required = [
        "admin:v2:add",
        "admin:v2:edit:200",
        "admin:v2:reserve:200",
        "admin:v2:publish:200",
        "admin:v2:unpublish:200",
        "admin:v2:delete:200",
        "admin:v2:order:confirm:5001",
        "admin:v2:order:reject:5001",
        "admin:v2:order:contacted:5001",
        "admin:v2:order:opened:5001",
        "admin:v2:order:complete:5001",
        "admin:v2:order:delete:5001",
        "admin:v2:backup:create",
        "admin:v2:backup:download:last",
        "admin:v2:danger:all",
        "admin:v2:settings:price",
    ]
    for data in manager_required:
        assert admin_v2._required_roles_for_callback(data) == {"owner", "manager"}

    assert admin_v2._required_roles_for_callback("admin:v2:backup:restore:3") == {"owner"}
    assert admin_v2._required_roles_for_callback("admin:v2:publish:text:200") is None
    assert admin_v2._required_roles_for_callback("admin:v2:profile:200") is None
    assert admin_v2._required_roles_for_callback("admin:v2:orders:0:pending") is None


def test_viewer_legacy_sensitive_callbacks_are_blocked():
    sensitive = [
        "admin:order:confirm:5001",
        "admin:order:reject:5001",
        "admin:order:contacted:5001",
        "admin:order:opened:5001",
        "admin:order:complete:5001",
        "admin:order:delete:5001",
        "admin:v2:backup:download:last",
    ]
    for callback in sensitive:
        assert admin_entry._viewer_blocked(callback) is True

    assert admin_router_legacy._parse_archive_reason_callback(
        "admin:v2:archive:reason:200:تمت الزيجة"
    ) == (200, "تمت الزيجة")
    assert admin_router_legacy._parse_reservation_extension_callback(
        "admin:v2:reservation:extend:200:14"
    ) == (200, 14)
    assert admin_router_legacy._parse_reservation_extension_request(
        "admin:v2:reservation:extend:200"
    ) == 200
    assert "admin_bottom" not in inspect.getsource(safe_routing)


def test_production_entrypoint_and_keyboards_are_inline_only():
    import app.main as production_main
    from app.keyboards import admin as admin_keyboard
    from app.keyboards import client as client_keyboard

    assert "admin_bottom" not in inspect.getsource(production_main)
    assert "ReplyKeyboardMarkup" not in inspect.getsource(admin_keyboard)
    assert "ReplyKeyboardMarkup" not in inspect.getsource(client_keyboard)
    assert "admin_bottom" not in inspect.getsource(safe_routing)
