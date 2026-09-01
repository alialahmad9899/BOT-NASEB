"""Admin keyboard builders (legacy-compatible + Admin V2 dashboard)."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:v2:add")],
        [InlineKeyboardButton("🔎 البحث الذكي", callback_data="admin:v2:search"), InlineKeyboardButton("📋 إدارة الإعلانات", callback_data="admin:v2:profiles:0:all")],
        [InlineKeyboardButton("💳 طلبات التواصل", callback_data="admin:v2:orders:0:pending"), InlineKeyboardButton("🔒 الحجوزات", callback_data="admin:v2:reservations:0")],
        [InlineKeyboardButton("🗃️ الأرشيف", callback_data="admin:v2:profiles:0:archived"), InlineKeyboardButton("⚠️ المعطلة", callback_data="admin:v2:profiles:0:inactive")],
        [InlineKeyboardButton("📊 التقارير", callback_data="admin:v2:reports"), InlineKeyboardButton("🧾 سجل العمليات", callback_data="admin:v2:audit")],
        [InlineKeyboardButton("💾 النسخ الاحتياطية", callback_data="admin:v2:backups"), InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin:v2:settings")],
    ])


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]])


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
        InlineKeyboardButton("✏️ تعديل", callback_data=f"admin:v2:edit:{request_number}"),
        InlineKeyboardButton("🗃️ أرشفة" if status != "inactive" else "♻️ إعادة تفعيل", callback_data=f"admin:v2:archive:{request_number}" if status != "inactive" else f"admin:v2:reactivate:{request_number}"),
    ]]
    rows.append([InlineKeyboardButton("📋 نص المنشور", callback_data=f"admin:v2:publish:text:{request_number}")])
    if status == "reserved":
        rows.append([InlineKeyboardButton("🔓 إلغاء الحجز", callback_data=f"admin:v2:unreserve:{request_number}")])
    elif status == "active":
        rows.append([InlineKeyboardButton("🔒 حجز العرض", callback_data=f"admin:v2:reserve:{request_number}")])
    rows.append([InlineKeyboardButton("⚠️ حذف نهائي", callback_data=f"admin:v2:delete:{request_number}")])
    rows.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def order_actions_keyboard(order_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 التفاصيل", callback_data=f"admin:v2:order:view:{order_number}"), InlineKeyboardButton("✅ تأكيد الدفع", callback_data=f"admin:v2:order:confirm:{order_number}")],
        [InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f"admin:v2:order:reject:{order_number}"), InlineKeyboardButton("🗑️ حذف الطلب", callback_data=f"admin:v2:order:delete:{order_number}")],
        [InlineKeyboardButton("⬅️ طلبات التواصل", callback_data="admin:v2:orders:0:pending")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def admin_orders_keyboard(order_numbers: list[int], has_pending: bool = True) -> InlineKeyboardMarkup:
    rows = []
    for number in order_numbers:
        rows.append([
            InlineKeyboardButton(f"🔎 {number}", callback_data=f"admin:v2:order:view:{number}"),
            InlineKeyboardButton("✅", callback_data=f"admin:v2:order:confirm:{number}"),
            InlineKeyboardButton("❌", callback_data=f"admin:v2:order:reject:{number}"),
            InlineKeyboardButton("🗑️", callback_data=f"admin:v2:order:delete:{number}"),
        ])
    if has_pending:
        rows.append([InlineKeyboardButton("🧹 إدارة الطلبات المعلّقة", callback_data="admin:v2:orders:0:pending")])
    rows.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data="admin:v2:orders:0:pending")])
    rows.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def confirm_delete_order_keyboard(order_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ نعم، احذف الطلب", callback_data=f"admin:v2:order:delete:{order_number}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"admin:v2:order:view:{order_number}")],
        [InlineKeyboardButton("⬅️ طلبات التواصل", callback_data="admin:v2:orders:0:pending")],
    ])


def confirm_delete_pending_orders_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ إدارة المعلّقة", callback_data="admin:v2:orders:0:pending")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:orders:0:pending")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def admin_delete_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 الأرشيف هو الحذف العادي", callback_data="admin:delete:selected")],
        [InlineKeyboardButton("⚠️ حذف نهائي", callback_data="admin:delete:all")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:delete:cancel")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")],
    ])


def confirm_delete_all_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ لا تستخدم الحذف المباشر", callback_data="admin:v2:profiles:0:all")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:menu")],
    ])


def confirm_delete_selected_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗃️ الذهاب للأرشيف", callback_data="admin:v2:profiles:0:archived")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:menu")],
    ])
