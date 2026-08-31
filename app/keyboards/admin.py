"""Admin keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:add")],
            [
                InlineKeyboardButton("🔎 البحث", callback_data="admin:search"),
                InlineKeyboardButton("📋 آخر الإعلانات", callback_data="admin:list"),
            ],
            [
                InlineKeyboardButton("✏️ تعديل إعلان", callback_data="admin:edit"),
                InlineKeyboardButton("🗑️ تعطيل إعلان", callback_data="admin:disable"),
            ],
            [InlineKeyboardButton("💳 الطلبات والمدفوعات", callback_data="admin:orders")],
            [
                InlineKeyboardButton("📊 الإحصائيات", callback_data="admin:stats"),
                InlineKeyboardButton("💾 نسخة احتياطية", callback_data="admin:backup"),
            ],
        ]
    )


def add_preview_keyboard(can_save: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if can_save:
        rows.append([InlineKeyboardButton("✅ حفظ الإعلان", callback_data="admin:add:save")])
    rows.extend([
        [InlineKeyboardButton("✏️ تعديل البيانات", callback_data="admin:add:edit")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:add:cancel")],
    ])
    return InlineKeyboardMarkup(rows)


def confirm_disable_keyboard(request_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ نعم، عطّل الإعلان", callback_data=f"admin:disable:confirm:{request_number}"),
            InlineKeyboardButton("❌ لا", callback_data="admin:disable:cancel"),
        ]
    ])


def profile_actions_keyboard(request_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ تعديل", callback_data=f"admin:edit:{request_number}"),
            InlineKeyboardButton("🗑️ تعطيل", callback_data=f"admin:disable:{request_number}"),
        ]
    ])


def order_actions_keyboard(order_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔎 التفاصيل", callback_data=f"admin:order:view:{order_number}"),
            InlineKeyboardButton("✅ تأكيد الدفع", callback_data=f"admin:order:confirm:{order_number}"),
        ],
        [InlineKeyboardButton("❌ رفض الدفع", callback_data=f"admin:order:reject:{order_number}")],
    ])
