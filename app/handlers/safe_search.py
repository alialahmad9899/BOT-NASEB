"""Safe admin natural-language search entry point."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.handlers import admin_v2
from app.services.profiles import normalize_digits

logger = logging.getLogger("bot-naseb.admin-search")

END = ConversationHandler.END
ADMIN_V2_INPUT = admin_v2.ADMIN_V2_INPUT


def prepare_admin_search_query(raw_text: str, ai_filters: Any | None = None) -> dict[str, Any]:
    """Build an admin search query and fix common Arabic colloquial phrases locally."""
    query = admin_v2._extract_admin_query(raw_text, ai_filters)
    normalized = normalize_digits(raw_text or "").strip().lower()

    # Deterministic gender fallback for common plural colloquial terms.
    if query["filters"].gender is None:
        if re.search(r"بنات|عرايس|صبايا|فتيات|نساء", normalized):
            query["filters"] = replace(query["filters"], gender="female")
        elif re.search(r"شباب|شبان|عرسان|رجال", normalized):
            query["filters"] = replace(query["filters"], gender="male")

    match = re.search(
        r"(?:عمر|العمر|عمرها|عمره|بعمر|سنها|سنه)\s*[:=-]?\s*(\d{1,3})\s*(?:و\s*)?(?:ما\s*)?(?:فوق|طالع|وما\s+فوق)",
        normalized,
    )
    if match:
        age = int(match.group(1))
        if 18 <= age <= 100:
            query["filters"] = replace(query["filters"], age_min=age, age_max=None)
    return query


def format_admin_search_preview(query: dict[str, Any]) -> str:
    filters = query["filters"]
    parts: list[str] = []
    if filters.gender:
        parts.append("👩 عروس" if filters.gender == "female" else "🤵 عريس")
    if filters.residence:
        parts.append(f"📍 السكن: {filters.residence}")
    if filters.age_min is not None and filters.age_max is not None:
        if filters.age_min == filters.age_max:
            parts.append(f"🎂 العمر: {filters.age_min} سنة")
        else:
            parts.append(f"🎂 العمر: {filters.age_min} إلى {filters.age_max} سنة")
    elif filters.age_min is not None:
        parts.append(f"🎂 العمر: من {filters.age_min} سنة وفوق")
    elif filters.age_max is not None:
        parts.append(f"🎂 العمر: حتى {filters.age_max} سنة")
    if filters.marital_status:
        parts.append(f"💍 الحالة: {filters.marital_status}")
    if filters.occupation:
        parts.append(f"💼 العمل: {filters.occupation}")
    if filters.education:
        parts.append(f"📚 التعليم: {filters.education}")
    for key, label in (("status", "📊 الحالة"), ("publication_status", "📤 النشر"), ("text_query", "🔎 نص")):
        value = query.get(key)
        if value:
            parts.append(f"{label}: {value}")
    return "🧠 فهمت البحث هيك:\n\n" + ("\n".join(parts) if parts else "🔎 بحث عام") + "\n\nهي المواصفات صحيحة؟"


async def admin_search_text(update: Any, context: Any) -> int:
    """Handle the search text message directly; no callback query is required."""
    raw_text = (update.effective_message.text or "").strip()
    ai = context.application.bot_data["ai_service"]
    ai_filters = None
    if ai.is_configured:
        try:
            ai_filters = await ai.parse_search_filters(raw_text)
        except Exception:
            logger.exception("Gemini search parsing failed; using deterministic parser")

    query = prepare_admin_search_query(raw_text, ai_filters)
    context.user_data["v2_search_query"] = query
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تنفيذ البحث", callback_data="admin:v2:search:execute:0")],
        [InlineKeyboardButton("✏️ تعديل البحث", callback_data="admin:v2:search")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ])
    await update.effective_message.reply_text(format_admin_search_preview(query), reply_markup=keyboard)
    return END
