from app.config import Settings


def test_settings_requires_token_and_at_least_one_admin(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("ADMIN_USER_IDS", "123")

    settings = Settings.from_env()

    assert settings.telegram_bot_token == "token"
    assert settings.admin_user_ids == frozenset({123})
    assert settings.ai_model == "gemini-3.5-flash-lite"
