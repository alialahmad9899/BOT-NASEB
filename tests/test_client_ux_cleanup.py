from app.handlers.client import WHATSAPP_CONFIRM, WHATSAPP_TEXT
from app.keyboards.client import client_main_keyboard, client_whatsapp_confirm_keyboard


def _texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_client_main_uses_plain_language_actions():
    texts = _texts(client_main_keyboard())
    assert texts[:6] == [
        "💗 بدي عروس",
        "🤵 بدي عريس",
        "🔎 بدي أبحث بنفسي",
        "📋 شوف العروض",
        "💳 طلباتي",
        "ℹ️ كيف بتشتغل الصفحة؟",
    ]


def test_whatsapp_confirmation_keyboard_has_only_simple_actions():
    assert "✅ نعم" in _texts(client_whatsapp_confirm_keyboard())
    assert "✏️ تعديل الرقم" in _texts(client_whatsapp_confirm_keyboard())
    assert "❌ إلغاء" in _texts(client_whatsapp_confirm_keyboard())
    callbacks = _callbacks(client_whatsapp_confirm_keyboard())
    assert "client:whatsapp:confirm" in callbacks
    assert "client:whatsapp:edit" in callbacks
    assert "client:whatsapp:cancel" in callbacks


def test_whatsapp_states_are_available_for_the_client_flow():
    assert WHATSAPP_TEXT != WHATSAPP_CONFIRM
