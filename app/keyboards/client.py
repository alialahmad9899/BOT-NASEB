"""Client keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def client_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💗 بدي عروس", callback_data="client:match:female")],
        [InlineKeyboardButton("🤵 بدي عريس", callback_data="client:match:male")],
        [InlineKeyboardButton("🔎 بدي أبحث بنفسي", callback_data="client:search")],
        [InlineKeyboardButton("📋 شوف العروض", callback_data="client:list")],
        [InlineKeyboardButton("💳 طلباتي", callback_data="client:orders")],
        [InlineKeyboardButton("ℹ️ كيف بتشتغل الصفحة؟", callback_data="client:about")],
    ])


def client_search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])


def client_search_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ إي، دور", callback_data="client:search:execute")],
        [InlineKeyboardButton("✏️ بدي عدّل", callback_data="client:search:edit")],
        [InlineKeyboardButton("🏠 رجوع", callback_data="client:menu")],
    ])


def client_no_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 عدّل البحث", callback_data="client:search")],
        [InlineKeyboardButton("🔎 بحث أوسع", callback_data="client:search:broaden")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="client:menu")],
    ])


def client_results_keyboard(request_numbers: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📌 عرض التفاصيل", callback_data=f"client:profile:{number}")]
        for number in request_numbers
    ]
    rows.extend([
        [InlineKeyboardButton("🔄 بحث جديد", callback_data="client:search")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def client_profile_keyboard(request_number: int, status: str = "active", has_results: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([InlineKeyboardButton("📩 أطلب التواصل", callback_data=f"client:request:{request_number}")])
    elif status == "reserved":
        rows.append([InlineKeyboardButton("🔒 العرض محجوز حالياً", callback_data="client:menu")])
    if has_results:
        rows.append([InlineKeyboardButton("⬅️ نتائج البحث", callback_data="client:results")])
    rows.extend([
        [InlineKeyboardButton("🔄 بحث جديد", callback_data="client:search")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def client_orders_keyboard(order_numbers: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"📌 عرض الطلب {number}", callback_data=f"client:order:view:{number}")]
        for number in order_numbers
    ]
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")])
    return InlineKeyboardMarkup(rows)


def client_order_detail_keyboard(order_status: str | None = None, order_number: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ طلباتي", callback_data="client:orders")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])


def client_payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 طلباتي", callback_data="client:orders")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])


def client_whatsapp_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء", callback_data="client:whatsapp:cancel")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])


def client_whatsapp_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data="client:whatsapp:confirm")],
        [InlineKeyboardButton("✏️ تعديل الرقم", callback_data="client:whatsapp:edit")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="client:whatsapp:cancel")],
    ])
