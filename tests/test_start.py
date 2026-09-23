import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import InlineKeyboardMarkup

from app.handlers.start import reset_session_for_start, start_command, start_content_for_user


def test_start_returns_admin_menu_for_admin_user():
    result = start_content_for_user(123, {123})

    assert result.role == "admin"
    assert "لوحة الأدمن" in result.text
    assert "اختار القسم اللي بدك تديره" in result.text


def test_start_returns_client_menu_for_regular_user():
    result = start_content_for_user(999, {123})

    assert result.role == "client"
    assert "لقاء ونصيب" in result.text
    assert "💗 بدي عروس" in result.text
    assert "🤵 بدي عريس" in result.text
    assert "🔎 بدي أبحث بنفسي" in result.text
    assert "📋 شوف العروض" in result.text
    assert "💳 طلباتي" in result.text
    assert "ℹ️ كيف بتشتغل الصفحة؟" in result.text
    assert "لوحة الأدمن" not in result.text


def test_start_session_reset_clears_previous_flow_state():
    context = type("Context", (), {})()
    context.user_data = {
        "client_flow": "search",
        "search_target_gender": "female",
        "pending_profile": "stale",
    }

    reset_session_for_start(context)

    assert context.user_data == {}


def test_admin_start_command_uses_inline_keyboard_only():
    reply_text = AsyncMock()
    context = SimpleNamespace(
        user_data={"stale_flow": "search"},
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(admin_user_ids=frozenset({123})),
            }
        ),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(reply_text=reply_text),
    )

    asyncio.run(start_command(update, context))

    reply_text.assert_awaited_once()
    markup = reply_text.await_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    assert context.user_data == {}


def test_database_backed_employee_is_detected_as_admin_command(monkeypatch):
    import app.handlers.start as start_module

    reply_text = AsyncMock()
    context = SimpleNamespace(
        user_data={"stale": "state"},
        application=SimpleNamespace(bot_data={"settings": SimpleNamespace()}),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1923538306),
        effective_message=SimpleNamespace(reply_text=reply_text),
    )

    monkeypatch.setattr(start_module, "effective_role", lambda context, user_id: "manager" if user_id == 1923538306 else None)
    asyncio.run(start_module.start_command(update, context))

    markup = reply_text.await_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    labels = "\n".join(button.text for row in markup.inline_keyboard for button in row)
    assert "admin" not in labels.lower()
    assert context.user_data == {}
