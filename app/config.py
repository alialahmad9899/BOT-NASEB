"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.services.admin_access import AdminAccess, build_admin_access
from app.services.permissions import parse_admin_user_ids


class SettingsError(ValueError):
    """Raised when required environment configuration is missing or invalid."""


DEFAULT_AI_MODEL = "gemini-3.5-flash-lite"
LEGACY_AI_MODELS = {"gemini-2.5-flash-lite"}


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_user_ids: frozenset[int]
    ai_api_key: str | None = None
    ai_model: str = DEFAULT_AI_MODEL
    database_url: str | None = None
    public_base_url: str | None = None
    webhook_secret: str | None = None
    webhook_path: str = "/telegram"
    port: int = 10000
    cham_cash_account: str = ""
    admin_owner_ids: frozenset[int] = frozenset()
    admin_manager_ids: frozenset[int] = frozenset()
    admin_viewer_ids: frozenset[int] = frozenset()
    admin_access: AdminAccess | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise SettingsError("TELEGRAM_BOT_TOKEN is required")

        legacy_ids = parse_admin_user_ids(os.getenv("ADMIN_USER_IDS", ""))
        if not legacy_ids:
            raise SettingsError("ADMIN_USER_IDS must contain at least one valid Telegram user ID")

        try:
            port = int(os.getenv("PORT", "10000"))
        except ValueError as exc:
            raise SettingsError("PORT must be an integer") from exc

        webhook_path = os.getenv("WEBHOOK_PATH", "/telegram").strip() or "/telegram"
        if not webhook_path.startswith("/"):
            webhook_path = "/" + webhook_path

        ai_model = os.getenv("AI_MODEL", DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
        if ai_model in LEGACY_AI_MODELS:
            ai_model = DEFAULT_AI_MODEL

        access = build_admin_access(
            os.getenv("ADMIN_USER_IDS", ""),
            os.getenv("ADMIN_OWNER_IDS", ""),
            os.getenv("ADMIN_MANAGER_IDS", ""),
            os.getenv("ADMIN_VIEWER_IDS", ""),
        )
        explicit_role_ids = set(access.owner_ids) | set(access.manager_ids) | set(access.viewer_ids)
        all_admin_ids = frozenset(set(legacy_ids) | explicit_role_ids)

        return cls(
            telegram_bot_token=token,
            admin_user_ids=all_admin_ids,
            ai_api_key=os.getenv("AI_API_KEY") or None,
            ai_model=ai_model,
            database_url=os.getenv("DATABASE_URL") or None,
            public_base_url=(os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or None),
            webhook_secret=os.getenv("WEBHOOK_SECRET") or None,
            webhook_path=webhook_path,
            port=port,
            cham_cash_account=os.getenv("CHAM_CASH_ACCOUNT", "").strip(),
            admin_owner_ids=access.owner_ids,
            admin_manager_ids=access.manager_ids,
            admin_viewer_ids=access.viewer_ids,
            admin_access=access,
        )
