"""Admin keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:add")],
        [InlineKeyboardButton("🔎 البحث", callback_data="admin:search"), InlineKeyboardButton("📋 آخر الإعلانات", callback_data="admin:list")],
        [InlineKeyboardButton("✏️ تعديل إعلان", callback_data="admin:edit"), InlineKeyboardButton("🗑️ تعطيل إعلان", callback_data="admin:disable")],
        [InlineKeyboardButton("🔒 إدارة الحجز", callback_data="admin:reservations")],
        [InlineKeyboardButton("🧹 حذف إعلانات", callback_data="admin:delete")],
        [InlineKeyboardButton("💳 الطلبات والمدفوعات", callback_data="admin:orders")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin:stats"), InlineKeyboardButton("💾 نسخة احتياطية", callback_data="admin:backup")],
    ])


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")]])


def add_preview_keyboard(can_save: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if can_save:
        rows.append([InlineKeyboardButton("✅ حفظ الإعلان", callback_data="admin:add:save")])
    rows.extend([
        [InlineKeyboardButton("✏️ تعديل البيانات", callback_data="admin:add:edit")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:add:cancel")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def confirm_disable_keyboard(request_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ نعم، عطّل الإعلان", callback_data=f"admin:disable:confirm:{request_number}"), InlineKeyboardButton("❌ لا", callback_data="admin:disable:cancel")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def profile_actions_keyboard(request_number: int, status: str = "active") -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton("✏️ تعديل", callback_data=f"admin:edit:{request_number}"),
        InlineKeyboardButton("🗑️ تعطيل", callback_data=f"admin:disable:{request_number}"),
    ]]
    if status == "reserved":
        rows.append([InlineKeyboardButton("🔓 إلغاء الحجز", callback_data=f"admin:unreserve:{request_number}")])
    elif status == "active":
        rows.append([InlineKeyboardButton("🔒 حجز العرض", callback_data=f"admin:reserve:{request_number}")])
    rows.append([InlineKeyboardButton("🗑️ حذف نهائي", callback_data=f"admin:delete:one:{request_number}")])
    rows.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def order_actions_keyboard(order_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 التفاصيل", callback_data=f"admin:order:view:{order_number}"), InlineKeyboardButton("✅ تأكيد الدفع", callback_data=f"admin:order:confirm:{order_number}")],
        [InlineKeyboardButton("❌ رفض الدفع", callback_data=f"admin:order:reject:{order_number}")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def confirm_delete_all_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ نعم، احذف الكل نهائياً", callback_data="admin:delete:all:confirm")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:delete:cancel")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def confirm_delete_selected_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ نعم، احذف المحدد", callback_data="admin:delete:selected:confirm")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:delete:cancel")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])
