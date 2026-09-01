"""`/start` routing and role-specific welcome text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.permissions import is_admin

if TYPE_CHECKING:
    from typing import Any


@dataclass(frozen=True)
class StartContent:
    role: Literal["admin", "client"]
    text: str


ADMIN_START_TEXT = """🔐 أهلاً في لوحة الأدمن – لقاء ونصيب

من هون فيك تدير عروض الزواج والبحث والطلبات.

➕ إضافة إعلان
🔎 البحث
📋 آخر الإعلانات
✏️ تعديل إعلان
🗑️ تعطيل إعلان
"""

CLIENT_START_TEXT = """🌸 أهلاً وسهلاً في لقاء ونصيب

اختر الخدمة اللي بدك ياها من القائمة تحت:

🔎 البحث عن عرض زواج
🤵 دورولي على عريس مناسب
👰 دورولي على عروس مناسبة
📋 تصفح العروض
ℹ️ طريقة العمل
"""


def start_content_for_user(user_id: int, admin_user_ids: set[int] | frozenset[int]) -> StartContent:
    if is_admin(user_id, admin_user_ids):
        return StartContent(role="admin", text=ADMIN_START_TEXT)
    return StartContent(role="client", text=CLIENT_START_TEXT)


async def start_command(update: Any, context: Any) -> None:
    # `/start` always acts as a clean restart, even when the user is inside a conversation.
    context.user_data.clear()
    user = update.effective_user
    message = update.effective_message
    settings = context.application.bot_data["settings"]
    content = start_content_for_user(user.id, settings.admin_user_ids)
    if content.role == "admin":
        from app.keyboards.admin import admin_main_keyboard
        keyboard = admin_main_keyboard()
    else:
        from app.keyboards.client import client_main_keyboard
        keyboard = client_main_keyboard()
    await message.reply_text(content.text, reply_markup=keyboard)
