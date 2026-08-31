"""`/start` routing and response content."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.permissions import is_admin

if TYPE_CHECKING:
    from typing import Any


@dataclass(frozen=True)
class StartContent:
    """Content selected for a user at `/start`."""

    role: Literal["admin", "client"]
    text: str


ADMIN_START_TEXT = """🔐 أهلاً في لوحة الأدمن – لقاء ونصيب

➕ إضافة إعلان
🔎 البحث
📋 عرض الإعلانات
✏️ تعديل إعلان
🗑️ حذف/تعطيل إعلان
"""

CLIENT_START_TEXT = """🌸 أهلاً وسهلاً في لقاء ونصيب

اختر الخدمة:

🔎 البحث عن عرض زواج
📋 تصفح العروض
ℹ️ طريقة العمل
"""


def start_content_for_user(
    user_id: int, admin_user_ids: set[int] | frozenset[int]
) -> StartContent:
    """Return the role-specific `/start` content without touching Telegram APIs."""
    if is_admin(user_id, admin_user_ids):
        return StartContent(role="admin", text=ADMIN_START_TEXT)
    return StartContent(role="client", text=CLIENT_START_TEXT)


async def start_command(update: Any, context: Any) -> None:
    """Handle `/start` using the application's centrally loaded settings."""
    user = update.effective_user
    message = update.effective_message
    settings = context.application.bot_data["settings"]
    content = start_content_for_user(user.id, settings.admin_user_ids)
    await message.reply_text(content.text, reply_markup=_keyboard_for_role(content.role))


def _keyboard_for_role(role: Literal["admin", "client"]):
    """Build the concrete Telegram keyboard lazily so pure tests need no Telegram import."""
    if role == "admin":
        from app.keyboards.admin import admin_main_keyboard

        return admin_main_keyboard()
    from app.keyboards.client import client_main_keyboard

    return client_main_keyboard()
