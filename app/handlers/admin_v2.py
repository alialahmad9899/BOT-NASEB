"""Admin V2 facade and operational dashboard.

The legacy admin implementation remains intact and is delegated to for old
callbacks. New functionality is additive and guarded by role-based access.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import delete, desc, func, or_, select
from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.database.admin_models import AdminAuditLog, AdminBackup, AdminSetting, OrderAdminMeta, ProfileAdminMeta
from app.database.models import Order, Profile, ProfileContact
from app.database.repositories import OrderRepository, ProfileRepository
from app.handlers import admin as legacy
from app.services.ai import AIExtractionError, AIService, ProfileExtraction, basic_profile_extraction
from app.services.admin_meta import (
    build_snapshot,
    create_backup,
    expire_reservations,
    get_order_meta,
    get_profile_meta,
    get_setting,
    list_audit_logs,
    list_backups,
    log_admin_action,
    metrics,
    payment_method,
    restore_snapshot,
    service_price,
    set_setting,
)
from app.services.duplicates import find_profile_duplicates
from app.services.permissions import is_admin
from app.services.profile_quality import score_profile
from app.services.profiles import ProfileDraft, apply_text_edits, extraction_to_draft, format_admin_profile, format_draft_preview, format_marriage_post, validate_profile_extraction
from app.services.search import filters_from_ai, merge_filters, parse_search_text

END = ConversationHandler.END
ADMIN_V2_INPUT = 100


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _settings(context: Any):
    return context.application.bot_data["settings"]


def _role(context: Any, user_id: int | None = None) -> str | None:
    user_id = user_id if user_id is not None else int(context._user_id) if getattr(context, "_user_id", None) else None
    settings = _settings(context)
    if user_id is None:
        return None
    access = getattr(settings, "admin_access", None)
    if access is not None:
        return access.role_for(user_id)
    return "owner" if is_admin(user_id, settings.admin_user_ids) else None


def _is_admin(update: Any, context: Any) -> bool:
    user = update.effective_user
    return bool(user and _role(context, user.id))


def _require_role(update: Any, context: Any, roles: set[str]) -> bool:
    user = update.effective_user
    return bool(user and _role(context, user.id) in roles)


def _remember_admin(context: Any, update: Any) -> None:
    user = update.effective_user
    if user:
        context._user_id = int(user.id)


def _audit(context: Any, action: str, entity_type: str | None = None, entity_number: int | None = None, details: dict[str, Any] | None = None) -> None:
    admin_id = getattr(context, "_user_id", None)
    if not admin_id:
        return
    try:
        with _session(context) as session:
            log_admin_action(session, int(admin_id), action, entity_type, entity_number, details)
            session.commit()
    except Exception:
        return


def _dashboard_text(data: dict[str, Any]) -> str:
    p, o = data["profiles"], data["orders"]
    return (
        "🔐 لوحة تحكم لقاء ونصيب\n\n"
        "📊 الملخص\n"
        f"✅ المتاحة: {p['active']}\n"
        f"🔒 المحجوزة: {p['reserved']}\n"
        f"⛔ المعطلة: {p['inactive']}\n"
        f"🗃️ الأرشيف: {p['archived']}\n\n"
        f"👩 العرائس: {p['female']} | 🤵 العرسان: {p['male']}\n\n"
        "💳 الطلبات\n"
        f"🆕 المعلقة: {o['pending']}\n"
        f"✅ المدفوعة: {o['paid']}\n"
        f"🤝 المكتملة: {o['completed']}\n"
        f"📈 التحويل إلى مكتمل: {o['conversion']}%\n\n"
        f"🆕 إعلانات اليوم: {p['today']}"
    )


def _dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:v2:add")],
        [InlineKeyboardButton("🔎 البحث الذكي", callback_data="admin:v2:search"), InlineKeyboardButton("📋 إدارة الإعلانات", callback_data="admin:v2:profiles:0:all")],
        [InlineKeyboardButton("💳 طلبات التواصل", callback_data="admin:v2:orders:0:pending"), InlineKeyboardButton("🔒 الحجوزات", callback_data="admin:v2:reservations:0")],
        [InlineKeyboardButton("🗃️ الأرشيف", callback_data="admin:v2:profiles:0:archived"), InlineKeyboardButton("⚠️ المعطلة", callback_data="admin:v2:profiles:0:inactive")],
        [InlineKeyboardButton("⚠️ بحاجة لاستكمال", callback_data="admin:v2:profiles:0:incomplete")],
        [InlineKeyboardButton("📊 التقارير", callback_data="admin:v2:reports"), InlineKeyboardButton("🧾 سجل العمليات", callback_data="admin:v2:audit")],
        [InlineKeyboardButton("💾 النسخ الاحتياطية", callback_data="admin:v2:backups"), InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin:v2:settings")],
        [InlineKeyboardButton("🛑 منطقة الخطر", callback_data="admin:v2:danger")],
    ])


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]])


def _profile_filter_title(name: str) -> str:
    return {
        "all": "كل الإعلانات",
        "active": "الإعلانات المتاحة",
        "reserved": "الإعلانات المحجوزة",
        "inactive": "الإعلانات المعطلة",
        "archived": "الأرشيف",
        "incomplete": "الإعلانات بحاجة لاستكمال",
    }.get(name, "الإعلانات")


def _profile_list_keyboard(rows, page: int, filter_name: str, has_next: bool) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(f"🔎 {row.request_number}", callback_data=f"admin:v2:profile:{row.request_number}")] for row in rows]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin:v2:profiles:{page - 1}:{filter_name}"))
    if has_next:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin:v2:profiles:{page + 1}:{filter_name}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    return InlineKeyboardMarkup(buttons)


def _filter_profiles(session, filter_name: str, limit: int, offset: int):
    stmt = select(Profile).order_by(desc(Profile.created_at))
    if filter_name in {"active", "reserved", "inactive"}:
        stmt = stmt.where(Profile.status == filter_name)
    elif filter_name == "archived":
        stmt = stmt.join(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).where(ProfileAdminMeta.archive_status == "archived")
    elif filter_name == "incomplete":
        stmt = stmt.join(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).where(ProfileAdminMeta.quality_score < 75)
    rows = list(session.scalars(stmt.offset(max(0, offset)).limit(limit + 1)).all())
    return rows[:limit], len(rows) > limit


def _profile_actions(request_number: int, status: str, publication_status: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("✏️ تعديل الحقول", callback_data=f"admin:v2:edit:{request_number}"), InlineKeyboardButton("📋 نص المنشور", callback_data=f"admin:v2:publish:text:{request_number}")],
    ]
    if status == "active":
        rows.append([InlineKeyboardButton("🔒 حجز العرض", callback_data=f"admin:v2:reserve:{request_number}")])
    if status == "reserved":
        rows.append([InlineKeyboardButton("🔓 إلغاء الحجز", callback_data=f"admin:v2:unreserve:{request_number}")])
    if status == "inactive":
        rows.append([InlineKeyboardButton("♻️ إعادة التفعيل", callback_data=f"admin:v2:reactivate:{request_number}")])
    if status != "inactive":
        rows.append([InlineKeyboardButton("📦 أرشفة", callback_data=f"admin:v2:archive:{request_number}")])
    if publication_status != "published":
        rows.append([InlineKeyboardButton("📤 اعتماد كمنشور", callback_data=f"admin:v2:publish:{request_number}")])
    else:
        rows.append([InlineKeyboardButton("↩️ إلغاء النشر", callback_data=f"admin:v2:unpublish:{request_number}")])
    rows.extend([
        [InlineKeyboardButton("⚠️ حذف نهائي", callback_data=f"admin:v2:delete:{request_number}")],
        [InlineKeyboardButton("⬅️ إدارة الإعلانات", callback_data="admin:v2:profiles:0:all")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ])
    return InlineKeyboardMarkup(rows)


def _edit_fields_keyboard(number: int) -> InlineKeyboardMarkup:
    fields = [
        ("الاسم", "name"), ("العمر", "age"), ("السكن", "residence"), ("الحالة", "marital_status"),
        ("الأولاد", "children_count"), ("العمل", "occupation"), ("التعليم", "education"),
        ("الطول", "height"), ("الوزن", "weight"), ("الشكل", "appearance"),
        ("مواصفات الشريك", "partner_requirements"), ("الهاتف", "phone"), ("واتساب", "whatsapp"),
        ("Telegram", "telegram_username"), ("الصورة", "photo"),
    ]
    buttons = [[InlineKeyboardButton(f"✏️ {label}", callback_data=f"admin:v2:editfield:{number}:{field}") for label, field in fields[i:i+2]] for i in range(0, len(fields), 2)]
    buttons.append([InlineKeyboardButton("⬅️ الإعلان", callback_data=f"admin:v2:profile:{number}")])
    return InlineKeyboardMarkup(buttons)


def _order_actions(order: Order, payment_state: str, contact_state: str) -> InlineKeyboardMarkup:
    buttons = []
    if payment_state == "pending":
        buttons.append([InlineKeyboardButton("💰 تأكيد الدفع", callback_data=f"admin:v2:order:confirm:{order.order_number}"), InlineKeyboardButton("❌ رفض الدفع", callback_data=f"admin:v2:order:reject:{order.order_number}")])
    if contact_state == "new":
        buttons.append([InlineKeyboardButton("📞 تم التواصل", callback_data=f"admin:v2:order:contacted:{order.order_number}")])
    if contact_state == "contacted":
        buttons.append([InlineKeyboardButton("🤝 فتح التواصل", callback_data=f"admin:v2:order:opened:{order.order_number}")])
    if contact_state == "opened":
        buttons.append([InlineKeyboardButton("✅ إغلاق الطلب", callback_data=f"admin:v2:order:complete:{order.order_number}")])
    if order.whatsapp:
        digits = re.sub(r"\D", "", order.whatsapp)
        if digits.startswith("0"): digits = "963" + digits[1:]
        buttons.append([InlineKeyboardButton("📱 فتح واتساب", url=f"https://wa.me/{digits}")])
    buttons.extend([
        [InlineKeyboardButton("🗑️ حذف الطلب", callback_data=f"admin:v2:order:delete:{order.order_number}")],
        [InlineKeyboardButton("⬅️ طلبات التواصل", callback_data="admin:v2:orders:0:pending")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ])
    return InlineKeyboardMarkup(buttons)


async def _dashboard(update: Any, context: Any) -> int:
    with _session(context) as session:
        expire_reservations(session)
        snapshot = metrics(session)
    await update.callback_query.edit_message_text(_dashboard_text(snapshot), reply_markup=_dashboard_keyboard())
    _audit(context, "dashboard_view")
    return END


def _build_backup_input(payload: bytes, filename: str) -> InputFile:
    return InputFile(payload, filename=filename)


# NOTE: Remaining Admin V2 implementation follows unchanged below.
