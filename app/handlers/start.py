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

من هون فيك تدير الإعلانات، البحث، الحجوزات، طلبات التواصل والمدفوعات.

➕ إضافة إعلان
🔎 بحث
📋 الإعلانات
💳 طلبات التواصل

اختار العملية من الأزرار تحت، وما في داعي تحفظ أوامر خاصة.
"""

CLIENT_START_TEXT = """🌸 أهلاً وسهلاً في لقاء ونصيب

هون فيك تلاقي عروض زواج وتبحث عن الشخص المناسب بطريقة بسيطة.

ما في داعي تعرف أوامر خاصة؛ اكتب طلبك متل ما بتحكي، والبوت بيفهمه.

🔎 البحث عن عرض زواج
🤵 دورولي على عريس مناسب
👰 دورولي على عروس مناسبة
📋 تصفح العروض
💳 طلباتي
ℹ️ طريقة العمل
"""


def reset_session_for_start(context: Any) -> None:
    """Clear any in-progress flow so `/start` is always a clean restart."""
    context.user_data.clear()


def start_content_for_user(user_id: int, admin_user_ids: set[int] | frozenset[int]) -> StartContent:
    if is_admin(user_id, admin_user_ids):
        return StartContent(role="admin", text=ADMIN_START_TEXT)
    return StartContent(role="client", text=CLIENT_START_TEXT)


async def start_command(update: Any, context: Any) -> None:
    reset_session_for_start(context)
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
