"""Administrative callback handlers with an explicit permission check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.permissions import is_admin

if TYPE_CHECKING:
    from typing import Any


def admin_action_allowed(user_id: int, admin_user_ids: set[int] | frozenset[int]) -> bool:
    """Pure policy function used by tests and the runtime guard."""
    return is_admin(user_id, admin_user_ids)


async def admin_callback(update: Any, context: Any) -> None:
    """Guard every admin callback before performing any administrative action."""
    query = update.callback_query
    settings = context.application.bot_data["settings"]
    user = query.from_user

    if not admin_action_allowed(user.id, settings.admin_user_ids):
        await query.answer("❌ ما عندك صلاحية لهالعملية.", show_alert=True)
        return

    await query.answer()
    await query.edit_message_text(
        "🛠️ هاي الوظيفة مجهزة بالواجهة حالياً، وتنفيذها بيبدأ بالمرحلة الخاصة فيها."
    )
