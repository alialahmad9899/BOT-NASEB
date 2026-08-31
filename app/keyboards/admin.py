"""Admin keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:add")],
            [
                InlineKeyboardButton("🔎 البحث", callback_data="admin:search"),
                InlineKeyboardButton("📋 عرض الإعلانات", callback_data="admin:list"),
            ],
            [
                InlineKeyboardButton("✏️ تعديل إعلان", callback_data="admin:edit"),
                InlineKeyboardButton("🗑️ حذف/تعطيل إعلان", callback_data="admin:disable"),
            ],
        ]
    )
