"""BOT-NASEB application package."""

from __future__ import annotations

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup as _TelegramInlineKeyboardMarkup


def _is_admin_keyboard(rows) -> bool:
    for row in rows or []:
        for button in row or []:
            callback_data = getattr(button, "callback_data", None)
            if isinstance(callback_data, str) and callback_data.startswith("admin:"):
                return True
    return False


def _admin_two_column_rows(rows):
    flat = [button for row in rows or [] for button in row or []]
    paired = [flat[index:index + 2] for index in range(0, len(flat), 2)]
    if paired and len(paired[-1]) == 1:
        last = paired[-1][0]
        callback_data = getattr(last, "callback_data", None)
        if callback_data == "admin:v2:dashboard":
            paired[-1].append(
                InlineKeyboardButton("🏠 الرئيسية", callback_data="admin:v2:dashboard")
            )
        else:
            paired[-1].append(
                InlineKeyboardButton("🏠 لوحة الأدمن", callback_data="admin:v2:dashboard")
            )
    return paired


class _AdminAwareInlineKeyboardMarkup(_TelegramInlineKeyboardMarkup):
    """Keep admin keyboards visually consistent at exactly two columns."""

    def __init__(self, inline_keyboard):
        rows = _admin_two_column_rows(inline_keyboard) if _is_admin_keyboard(inline_keyboard) else inline_keyboard
        super().__init__(rows)


# Handler modules import InlineKeyboardMarkup from telegram after the package is
# initialized, so the policy applies automatically without touching client UI.
import telegram as _telegram

_telegram.InlineKeyboardMarkup = _AdminAwareInlineKeyboardMarkup
