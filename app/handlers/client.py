"""Client-facing callback handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


async def client_callback(update: Any, context: Any) -> None:
    """Handle client menu actions without exposing private profile data."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🌸 هاي الخدمة قيد التجهيز، ورح تنضاف ضمن مراحل البوت الجاية."
    )
