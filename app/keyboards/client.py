"""Client keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def client_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔎 البحث عن عرض زواج", callback_data="client:search")],
            [InlineKeyboardButton("💗 دورولي على شريك مناسب", callback_data="client:match")],
            [InlineKeyboardButton("📋 تصفح العروض", callback_data="client:list")],
            [InlineKeyboardButton("ℹ️ طريقة العمل", callback_data="client:about")],
        ]
    )


def client_profile_keyboard(request_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 طلب تواصل", callback_data=f"client:request:{request_number}")],
        [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="client:menu")],
    ])


def client_results_keyboard(request_numbers: list[int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📌 طلب {number}", callback_data=f"client:profile:{number}")]
        for number in request_numbers
    ])
