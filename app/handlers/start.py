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


ADMIN_START_TEXT = """🔐 أهلاً وسهلاً في لوحة الأدمن – لقاء ونصيب

من هون بتدير كل شغل الصفحة بطريقة مرتبة وبسيطة.

📊 الحالة الحالية بتظهر هون، وكل وظيفة موجودة ضمن قسمها.

اختار القسم اللي بدك تديره 👇
"""

CLIENT_START_TEXT = """🌸 أهلاً وسهلاً في لقاء ونصيب

منساعدك تلاقي الشخص المناسب بطريقة بسيطة ❤️

شو حابب تعمل؟

💗 بدي عروس
🤵 بدي عريس

🔎 بدي أبحث بنفسي
📋 شوف العروض
💳 طلباتي
ℹ️ كيف بتشتغل الصفحة؟
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
