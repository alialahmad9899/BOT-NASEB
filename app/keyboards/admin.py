"""Admin keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:add")],
        [InlineKeyboardButton("🔎 البحث", callback_data="admin:search"), InlineKeyboardButton("📋 الإعلانات", callback_data="admin:list")],
        [InlineKeyboardButton("✏️ تعديل إعلان", callback_data="admin:edit"), InlineKeyboardButton("⛔ تعطيل إعلان", callback_data="admin:disable")],
        [InlineKeyboardButton("🔒 الحجوزات", callback_data="admin:reservations")],
        [InlineKeyboardButton("🧹 حذف إعلانات", callback_data="admin:delete")],
        [InlineKeyboardButton("💳 طلبات التواصل", callback_data="admin:orders")],
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
        [InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f"admin:order:reject:{order_number}"), InlineKeyboardButton("🗑️ حذف الطلب", callback_data=f"admin:order:delete:{order_number}")],
        [InlineKeyboardButton("⬅️ طلبات التواصل", callback_data="admin:orders")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def admin_orders_keyboard(order_numbers: list[int], has_pending: bool = True) -> InlineKeyboardMarkup:
    rows = []
    for number in order_numbers:
        rows.append([
            InlineKeyboardButton(f"🔎 {number}", callback_data=f"admin:order:view:{number}"),
            InlineKeyboardButton("✅", callback_data=f"admin:order:confirm:{number}"),
            InlineKeyboardButton("❌", callback_data=f"admin:order:reject:{number}"),
            InlineKeyboardButton("🗑️", callback_data=f"admin:order:delete:{number}"),
        ])
    if has_pending:
        rows.append([InlineKeyboardButton("🧹 حذف كل الطلبات المعلّقة", callback_data="admin:orders:delete:pending")])
    rows.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data="admin:orders")])
    rows.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def confirm_delete_order_keyboard(order_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ نعم، احذف الطلب", callback_data=f"admin:order:delete:confirm:{order_number}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"admin:order:view:{order_number}")],
        [InlineKeyboardButton("⬅️ طلبات التواصل", callback_data="admin:orders")],
    ])


def confirm_delete_pending_orders_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ نعم، احذف كل المعلّقة", callback_data="admin:orders:delete:pending:confirm")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:orders")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def admin_delete_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ حذف طلبات محددة", callback_data="admin:delete:selected")],
        [InlineKeyboardButton("⚠️ حذف جميع الإعلانات", callback_data="admin:delete:all")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:delete:cancel")],
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
