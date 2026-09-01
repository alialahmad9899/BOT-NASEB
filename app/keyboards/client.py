"""Client keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def client_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 البحث عن عرض زواج", callback_data="client:search")],
        [InlineKeyboardButton("🤵 دورولي على عريس مناسب", callback_data="client:match:male")],
        [InlineKeyboardButton("👰 دورولي على عروس مناسبة", callback_data="client:match:female")],
        [InlineKeyboardButton("📋 تصفح العروض", callback_data="client:list")],
        [InlineKeyboardButton("💳 طلباتي", callback_data="client:orders")],
        [InlineKeyboardButton("ℹ️ طريقة العمل", callback_data="client:about")],
    ])


def client_search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="client:menu")],
    ])


def client_search_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ابحث بهالمواصفات", callback_data="client:search:execute")],
        [InlineKeyboardButton("✏️ عدّل البحث", callback_data="client:search:edit")],
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="client:menu")],
    ])


def client_no_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 عدّل البحث", callback_data="client:search")],
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="client:menu")],
    ])


def client_results_keyboard(request_numbers: list[int]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📌 عرض الطلب {number}", callback_data=f"client:profile:{number}")] for number in request_numbers]
    rows.extend([
        [InlineKeyboardButton("🔄 بحث جديد", callback_data="client:search")],
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="client:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def client_profile_keyboard(request_number: int, status: str = "active", has_results: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([InlineKeyboardButton("📩 طلب تواصل", callback_data=f"client:request:{request_number}")])
    elif status == "reserved":
        rows.append([InlineKeyboardButton("🔒 العرض محجوز حالياً", callback_data="client:menu")])
    if has_results:
        rows.append([InlineKeyboardButton("⬅️ نتائج البحث", callback_data="client:results")])
    rows.extend([
        [InlineKeyboardButton("🔄 بحث جديد", callback_data="client:search")],
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="client:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def client_orders_keyboard(order_numbers: list[int]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"💳 طلب دفع {number}", callback_data=f"client:order:view:{number}")] for number in order_numbers]
    rows.append([InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="client:menu")])
    return InlineKeyboardMarkup(rows)


def client_order_detail_keyboard(order_status: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if order_status == "pending_payment":
        rows.append([InlineKeyboardButton("💳 إدخال رقم العملية", callback_data="client:payment:submit")])
    rows.extend([
        [InlineKeyboardButton("⬅️ طلباتي", callback_data="client:orders")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="client:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def client_payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 إدخال رقم العملية", callback_data="client:payment:submit")],
        [InlineKeyboardButton("✖️ إلغاء إدخال العملية", callback_data="client:payment:cancel")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="client:menu")],
    ])
