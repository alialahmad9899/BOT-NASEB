"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.services.permissions import parse_admin_user_ids


class SettingsError(ValueError):
    """Raised when required environment configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_user_ids: frozenset[int]
    ai_api_key: str | None = None
    ai_model: str = "gemini-2.5-flash-lite"
    database_url: str | None = None
    public_base_url: str | None = None
    webhook_secret: str | None = None
    webhook_path: str = "/telegram"
    port: int = 10000
    cham_cash_account: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise SettingsError("TELEGRAM_BOT_TOKEN is required")

        admin_user_ids = parse_admin_user_ids(os.getenv("ADMIN_USER_IDS", ""))
        if not admin_user_ids:
            raise SettingsError("ADMIN_USER_IDS must contain at least one valid Telegram user ID")

        try:
            port = int(os.getenv("PORT", "10000"))
        except ValueError as exc:
            raise SettingsError("PORT must be an integer") from exc

        webhook_path = os.getenv("WEBHOOK_PATH", "/telegram").strip() or "/telegram"
        if not webhook_path.startswith("/"):
            webhook_path = "/" + webhook_path

        return cls(
            telegram_bot_token=token,
            admin_user_ids=frozenset(admin_user_ids),
            ai_api_key=os.getenv("AI_API_KEY") or None,
            ai_model=os.getenv("AI_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite",
            database_url=os.getenv("DATABASE_URL") or None,
            public_base_url=(os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or None),
            webhook_secret=os.getenv("WEBHOOK_SECRET") or None,
            webhook_path=webhook_path,
            port=port,
            cham_cash_account=os.getenv("CHAM_CASH_ACCOUNT", "").strip(),
        )
