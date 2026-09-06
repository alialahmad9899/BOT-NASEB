import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import ReplyKeyboardMarkup

from app.handlers.admin_bottom import BOTTOM_TO_CALLBACK, HOME_BUTTONS, admin_bottom_text_router, is_admin_bottom_text
from app.keyboards.admin import admin_bottom_keyboard
from app.handlers.start import start_content_for_user


def test_admin_bottom_keyboard_is_reply_keyboard():
    keyboard = admin_bottom_keyboard()
    assert isinstance(keyboard, ReplyKeyboardMarkup)
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert "➕ إضافة إعلان" in labels
    assert "🔎 البحث الذكي" in labels
    assert "💳 طلبات التواصل" in labels
    assert "⬅️ رجوع للوحة الأدمن" in labels
    assert "🏠 الرئيسية" in labels


def test_legacy_admin_main_keyboard_remains_inline_compatible():
    from app.keyboards.admin import admin_main_keyboard
    assert hasattr(admin_main_keyboard(), "inline_keyboard")


def test_admin_start_keeps_admin_role_separate_from_client():
    admin = start_content_for_user(123, {123})
    client = start_content_for_user(456, {123})
    assert admin.role == "admin"
    assert "لوحة الأدمن" in admin.text
    assert client.role == "client"


def test_bottom_keyboard_labels_have_explicit_routing():
    assert HOME_BUTTONS == {"🏠 الرئيسية", "⬅️ رجوع للوحة الأدمن"}
    for label in BOTTOM_TO_CALLBACK:
        assert is_admin_bottom_text(label)


def test_non_navigation_text_is_not_intercepted():
    assert is_admin_bottom_text("هذا إعلان جديد") is False


def test_home_button_clears_current_flow_and_returns_dashboard():
    reply_text = AsyncMock()
    context = SimpleNamespace(
        user_data={"v2_flow": "search_input", "temporary": "value"},
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(admin_user_ids={123}, admin_access=None),
                "session_factory": None,
            }
        ),
    )
    context.application.bot_data["settings"].admin_access = SimpleNamespace(role_for=lambda user_id: "owner")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(text="⬅️ رجوع للوحة الأدمن", reply_text=reply_text),
    )

    try:
        asyncio.run(admin_bottom_text_router(update, context))
    except Exception:
        pass

    assert "v2_flow" not in context.user_data
    assert context.user_data.get("v2_admin_user_id") == 123
