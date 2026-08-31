"""Client keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def client_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔎 البحث عن عرض زواج", callback_data="client:search")],
            [InlineKeyboardButton("📋 تصفح العروض", callback_data="client:list")],
            [InlineKeyboardButton("ℹ️ طريقة العمل", callback_data="client:about")],
        ]
    )
