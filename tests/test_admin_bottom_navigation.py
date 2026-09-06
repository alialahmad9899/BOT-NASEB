from telegram import ReplyKeyboardMarkup

from app.keyboards.admin import admin_main_keyboard
from app.handlers.start import start_content_for_user


def test_admin_main_keyboard_is_bottom_reply_keyboard():
    keyboard = admin_main_keyboard()

    assert isinstance(keyboard, ReplyKeyboardMarkup)
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert "➕ إضافة إعلان" in labels
    assert "🔎 البحث الذكي" in labels
    assert "💳 طلبات التواصل" in labels
    assert "⬅️ رجوع للوحة الأدمن" in labels
    assert "🏠 الرئيسية" in labels


def test_admin_start_keeps_navigation_intent_separate_from_client_start():
    admin = start_content_for_user(123, {123})
    client = start_content_for_user(456, {123})

    assert admin.role == "admin"
    assert "لوحة الأدمن" in admin.text
    assert client.role == "client"
