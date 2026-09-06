"""Persistent bottom-keyboard navigation for the admin UI."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.handlers import admin_v2
from app.handlers.safe_routing import admin_callback_router
from app.services.admin_meta import expire_reservations, metrics
from app.services.permissions import is_admin

BOTTOM_TO_CALLBACK = {
    "➕ إضافة إعلان": "admin:v2:add",
    "🔎 البحث الذكي": "admin:v2:search",
    "📋 إدارة الإعلانات": "admin:v2:profiles:0:all",
    "💳 طلبات التواصل": "admin:v2:orders:0:pending",
    "🔒 الحجوزات": "admin:v2:reservations:0",
    "🗃️ الأرشيف": "admin:v2:profiles:0:archived",
    "⚠️ المعطلة": "admin:v2:profiles:0:inactive",
    "📊 التقارير": "admin:v2:reports",
    "🧾 سجل العمليات": "admin:v2:audit",
    "💾 النسخ الاحتياطية": "admin:v2:backups",
    "⚙️ الإعدادات": "admin:v2:settings",
}

HOME_BUTTONS = {"🏠 الرئيسية", "⬅️ رجوع للوحة الأدمن"}


def is_admin_bottom_text(text: str | None) -> bool:
    return bool(text and (text.strip() in HOME_BUTTONS or text.strip() in BOTTOM_TO_CALLBACK))


def _dashboard_text(context: Any) -> str:
    with context.application.bot_data["session_factory"]() as session:
        expire_reservations(session)
        snapshot = metrics(session)
    return admin_v2._dashboard_text(snapshot)


class _MessageCallbackProxy:
    """Adapt a reply-keyboard message into the callback interface used by Admin V2."""

    def __init__(self, update: Any, data: str) -> None:
        self._update = update
        self.data = data
        self.message = update.effective_message

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def edit_message_text(self, text: str, *args: Any, **kwargs: Any) -> Any:
        kwargs.pop("reply_markup", None)
        from app.keyboards.admin import admin_main_keyboard
        return await self._update.effective_message.reply_text(
            text,
            *args,
            reply_markup=admin_main_keyboard(),
            **kwargs,
        )


async def admin_bottom_text_router(update: Any, context: Any) -> int | None:
    text = (getattr(getattr(update, "effective_message", None), "text", None) or "").strip()
    if not is_admin_bottom_text(text):
        return None

    user = update.effective_user
    settings = context.application.bot_data["settings"]
    if user is None or not is_admin(int(user.id), settings.admin_user_ids):
        return None

    # Bottom navigation is global: pressing it cancels an in-progress admin flow.
    context.user_data.clear()
    context.user_data["v2_admin_user_id"] = int(user.id)

    if text in HOME_BUTTONS:
        from app.keyboards.admin import admin_main_keyboard
        await update.effective_message.reply_text(
            _dashboard_text(context),
            reply_markup=admin_main_keyboard(),
        )
        return admin_v2.END

    callback_data = BOTTOM_TO_CALLBACK[text]
    proxy = _MessageCallbackProxy(update, callback_data)
    callback_update = SimpleNamespace(
        callback_query=proxy,
        effective_user=update.effective_user,
        effective_message=update.effective_message,
    )
    return await admin_callback_router(callback_update, context)
