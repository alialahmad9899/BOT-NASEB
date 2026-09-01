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
from telegram import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
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
    role = _role(context, user.id if user else None)
    if role not in roles:
        if getattr(update, "callback_query", None):
            return False
        return False
    return True


def _audit(context: Any, action: str, entity_type: str | None = None, entity_number: int | None = None, details: str | dict | None = None) -> None:
    user_id = getattr(getattr(context, "_user_id", None), "__int__", lambda: None)()
    if user_id is None:
        user_data = getattr(context, "user_data", {}) or {}
        user_id = user_data.get("v2_admin_user_id")
    if not user_id:
        return
    try:
        with _session(context) as session:
            log_admin_action(session, int(user_id), action, entity_type, entity_number, details)
            session.commit()
    except Exception:
        pass


def _remember_admin(context: Any, update: Any) -> None:
    if update.effective_user:
        context.user_data["v2_admin_user_id"] = int(update.effective_user.id)


def _dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:v2:add")],
        [InlineKeyboardButton("🔎 البحث الذكي", callback_data="admin:v2:search"), InlineKeyboardButton("📋 إدارة الإعلانات", callback_data="admin:v2:profiles:0:all")],
        [InlineKeyboardButton("💳 طلبات التواصل", callback_data="admin:v2:orders:0:pending"), InlineKeyboardButton("🔒 الحجوزات", callback_data="admin:v2:reservations:0")],
        [InlineKeyboardButton("🗃️ الأرشيف", callback_data="admin:v2:profiles:0:archived"), InlineKeyboardButton("⚠️ المعطلة", callback_data="admin:v2:profiles:0:inactive")],
        [InlineKeyboardButton("📊 التقارير", callback_data="admin:v2:reports"), InlineKeyboardButton("🧾 سجل العمليات", callback_data="admin:v2:audit")],
        [InlineKeyboardButton("💾 النسخ الاحتياطية", callback_data="admin:v2:backups"), InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin:v2:settings")],
    ])


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]])


def _dashboard_text(snapshot: dict[str, Any]) -> str:
    p = snapshot["profiles"]
    o = snapshot["orders"]
    return (
        "🔐 لوحة تحكم لقاء ونصيب\n\n"
        "📊 ملخص سريع\n\n"
        f"✅ المتاحة: {p['active']}\n"
        f"🔒 المحجوزة: {p['reserved']}\n"
        f"⛔ المعطلة: {p['inactive']}\n"
        f"🗃️ المؤرشفة: {p['archived']}\n\n"
        f"🆕 إعلانات اليوم: {p['today']}\n"
        f"🆕 إعلانات هذا الأسبوع: {p['week']}\n"
        f"🆕 إعلانات هذا الشهر: {p['month']}\n\n"
        f"💳 بانتظار المتابعة: {o['pending']}\n"
        f"💰 مدفوعة: {o['paid']}\n"
        f"✅ مكتملة: {o['completed']}\n"
        f"📈 نسبة الإكمال من المدفوع: {o['conversion']}%"
    )


def _profile_filter_title(filter_name: str) -> str:
    return {
        "all": "كل الإعلانات", "female": "العرائس", "male": "العرسان", "active": "المتاحة",
        "reserved": "المحجوزة", "inactive": "المعطلة", "archived": "الأرشيف", "ready": "جاهزة للنشر", "published": "المنشورة",
    }.get(filter_name, "الإعلانات")


def _parse_page(data: str, marker: str, default: int = 0) -> int:
    try:
        return int(data.rsplit(marker, 1)[1])
    except (ValueError, IndexError):
        return default


def _profile_list_keyboard(rows: list[Profile], page: int, filter_name: str, has_next: bool) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(f"📌 {row.request_number} — {row.name or 'بدون اسم'}", callback_data=f"admin:v2:profile:{row.request_number}")] for row in rows]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin:v2:profiles:{page-1}:{filter_name}"))
    if has_next:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin:v2:profiles:{page+1}:{filter_name}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔎 بحث", callback_data="admin:v2:search")])
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    return InlineKeyboardMarkup(buttons)


def _filter_profiles(session, filter_name: str, limit: int, offset: int) -> tuple[list[Profile], bool]:
    stmt = select(Profile).order_by(desc(Profile.created_at))
    if filter_name == "female": stmt = stmt.where(Profile.gender == "female")
    elif filter_name == "male": stmt = stmt.where(Profile.gender == "male")
    elif filter_name in {"active", "reserved", "inactive"}: stmt = stmt.where(Profile.status == filter_name)
    elif filter_name == "archived": stmt = stmt.join(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).where(ProfileAdminMeta.archive_status == "archived")
    elif filter_name == "ready": stmt = stmt.join(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).where(ProfileAdminMeta.publication_status == "ready")
    elif filter_name == "published": stmt = stmt.join(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).where(ProfileAdminMeta.publication_status == "published")
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


async def _show_profiles(update: Any, context: Any, page: int, filter_name: str) -> int:
    with _session(context) as session:
        rows, has_next = _filter_profiles(session, filter_name, 10, page * 10)
    title = _profile_filter_title(filter_name)
    if not rows:
        await update.callback_query.edit_message_text(f"📋 {title}\n\nما في إعلانات بهالقسم.", reply_markup=_dashboard_keyboard())
        return END
    text = f"📋 {title}\n\n" + "\n".join(
        f"📌 {row.request_number} — {row.name or 'بدون اسم'} — {row.age} سنة — {row.residence} — {'🔒 محجوز' if row.status == 'reserved' else '⛔ معطّل' if row.status == 'inactive' else '✅ متاح'}"
        for row in rows
    )
    await update.callback_query.edit_message_text(text, reply_markup=_profile_list_keyboard(rows, page, filter_name, has_next))
    return END


async def _show_profile(update: Any, context: Any, number: int) -> int:
    with _session(context) as session:
        profile = ProfileRepository(session).get_with_contact(number)
        if profile is None:
            await update.callback_query.edit_message_text("❌ ما لقينا هالإعلان.", reply_markup=_dashboard_keyboard())
            return END
        meta = get_profile_meta(session, int(profile["id"]), create=True)
        quality = score_profile(ProfileDraft({k: profile.get(k) for k in ("gender", "name", "age", "residence", "marital_status", "children_count", "occupation", "education", "height", "weight", "appearance", "partner_requirements", "photo_file_id")}, {k: profile.get(k) for k in ("phone", "telegram_username", "whatsapp")}))
        session.commit()
    text = format_admin_profile(profile) + (
        f"\n\n⭐ جودة الإعلان: {quality.score}/100\n"
        f"📤 حالة النشر: {meta.publication_status}\n"
        f"🗃️ الأرشيف: {meta.archive_status}"
    )
    if quality.missing_fields:
        text += "\n⚠️ نواقص: " + "، ".join(quality.missing_fields)
    if quality.warnings:
        text += "\n💡 ملاحظات: " + "، ".join(quality.warnings[:4])
    await update.callback_query.edit_message_text(text, reply_markup=_profile_actions(number, profile.get("status", "active"), meta.publication_status))
    return END


async def _start_add(update: Any, context: Any) -> int:
    context.user_data.clear()
    _remember_admin(context, update)
    context.user_data["v2_flow"] = "add_raw"
    await update.callback_query.edit_message_text("➕ إضافة إعلان\n\nابعتلي الإعلان الخام مثل ما وصلك. فيك تبعته نص أو صورة معها Caption، وأنا برتبه وبفحص التكرار والنواقص قبل الحفظ.", reply_markup=_back_keyboard())
    return ADMIN_V2_INPUT


async def _parse_add(update: Any, context: Any, raw_text: str, photo_file_id: str | None = None) -> int:
    ai: AIService = context.application.bot_data["ai_service"]
    deterministic = basic_profile_extraction(raw_text, photo_file_id)
    if not ai.is_configured:
        await update.effective_message.reply_text("⚠️ Gemini مو مهيأ حالياً، لذلك ما رح أخمّن بيانات الإعلان.", reply_markup=_back_keyboard())
        return ADMIN_V2_INPUT
    try:
        extraction = await AIService.resolve_profile_extraction(ai, raw_text, deterministic)
    except AIExtractionError:
        await update.effective_message.reply_text("⚠️ ما قدرت أوصل لـGemini لتنظيم الإعلان. ما تم حفظ أي بيانات.", reply_markup=_back_keyboard())
        return ADMIN_V2_INPUT
    if photo_file_id and not extraction.photo_file_id:
        extraction = extraction.model_copy(update={"photo_file_id": photo_file_id})
    draft = extraction_to_draft(extraction)
    with _session(context) as session:
        number = ProfileRepository(session).peek_next_request_number()
        duplicates = find_profile_duplicates(session, draft)
    quality = score_profile(draft)
    context.user_data["v2_draft"] = draft
    context.user_data["v2_pending_number"] = number
    context.user_data["v2_quality"] = quality
    context.user_data["v2_duplicate_matches"] = duplicates
    context.user_data["v2_duplicate_ack"] = False
    return await _show_add_preview(update, context)


async def _show_add_preview(update: Any, context: Any) -> int:
    draft: ProfileDraft = context.user_data.get("v2_draft")
    if draft is None:
        return END
    extraction = ProfileExtraction.model_validate({**draft.public_data, **draft.private_contact_data})
    validation = validate_profile_extraction(extraction, draft.private_contact_data)
    quality = score_profile(draft)
    text = format_draft_preview(draft, request_number=context.user_data.get("v2_pending_number"))
    text += f"\n\n⭐ تقييم الجودة: {quality.score}/100"
    if quality.missing_fields:
        text += "\n⚠️ النواقص: " + "، ".join(quality.missing_fields)
    if quality.warnings:
        text += "\n💡 " + "\n💡 ".join(quality.warnings[:5])
    duplicates = context.user_data.get("v2_duplicate_matches") or []
    if duplicates and not context.user_data.get("v2_duplicate_ack"):
        text += "\n\n⚠️ لقيت إعلانات مشابهة:\n" + "\n".join(f"📌 {d.request_number} — {d.name or 'بدون اسم'} — {d.age} سنة — {d.residence} — تشابه {d.score}%" for d in duplicates[:3])
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ مو نفس الشخص، كمّل", callback_data="admin:v2:add:duplicate:continue")],
            [InlineKeyboardButton("✅ نفس الشخص، إلغاء الإضافة", callback_data="admin:v2:add:duplicate:cancel")],
            [InlineKeyboardButton("✏️ تعديل البيانات", callback_data="admin:v2:add:edit")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:add:cancel")],
        ])
    else:
        save_enabled = validation.ok
        keyboard_rows = []
        if save_enabled:
            keyboard_rows.append([InlineKeyboardButton("✅ حفظ الإعلان", callback_data="admin:v2:add:save")])
        keyboard_rows += [
            [InlineKeyboardButton("🤖 تحسين الإعلان", callback_data="admin:v2:add:improve"), InlineKeyboardButton("✏️ تعديل البيانات", callback_data="admin:v2:add:edit")],
            [InlineKeyboardButton("🔍 فحص التكرار", callback_data="admin:v2:add:duplicates"), InlineKeyboardButton("📋 نص المنشور", callback_data="admin:v2:add:publish_text")],
            [InlineKeyboardButton("🟢 جاهز للنشر", callback_data="admin:v2:add:ready")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:add:cancel")],
        ]
        keyboard = InlineKeyboardMarkup(keyboard_rows)
    if update.callback_query:
        await update.callback_query.edit_message_text(text + "\n\nهل تريد المتابعة؟", reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text + "\n\nهل تريد المتابعة؟", reply_markup=keyboard)
    return ADMIN_V2_INPUT


async def _save_add(update: Any, context: Any) -> int:
    draft: ProfileDraft = context.user_data.get("v2_draft")
    if draft is None:
        await update.callback_query.edit_message_text("❌ ما في مسودة للحفظ.", reply_markup=_dashboard_keyboard())
        return END
    extraction = ProfileExtraction.model_validate({**draft.public_data, **draft.private_contact_data})
    validation = validate_profile_extraction(extraction, draft.private_contact_data)
    if not validation.ok:
        await update.callback_query.edit_message_text("⚠️ الإعلان ناقص. كمّل البيانات الأساسية قبل الحفظ.", reply_markup=_dashboard_keyboard())
        return END
    number = int(context.user_data.get("v2_pending_number"))
    with _session(context) as session:
        if ProfileRepository(session).get(number) is not None:
            await update.callback_query.edit_message_text("⚠️ رقم الإعلان تغيّر أثناء المعاينة. أعد الإضافة مرة ثانية.", reply_markup=_dashboard_keyboard())
            return END
        profile = ProfileRepository(session).create(draft, request_number=number)
        meta = get_profile_meta(session, int(profile.id), create=True)
        quality = score_profile(draft)
        meta.quality_score = quality.score
        meta.publication_status = "ready" if quality.ready else "review"
        log_admin_action(session, int(update.effective_user.id), "profile_add", "profile", number, {"quality": quality.score})
        session.commit()
    context.user_data.clear()
    await update.callback_query.edit_message_text(f"✅ تم حفظ الإعلان بنجاح.\n\n📌 رقم الإعلان: {number}\n⭐ الجودة: {quality.score}/100\n📤 الحالة: {'جاهز للنشر' if quality.ready else 'قيد المراجعة'}", reply_markup=_dashboard_keyboard())
    return END


async def _improve_draft(update: Any, context: Any) -> int:
    draft: ProfileDraft = context.user_data.get("v2_draft")
    ai: AIService = context.application.bot_data["ai_service"]
    if draft is None:
        return END
    if not ai.is_configured:
        await update.callback_query.edit_message_text("⚠️ Gemini مو متاح حالياً.", reply_markup=_dashboard_keyboard())
        return END
    source = format_marriage_post(dict(draft.public_data, request_number=context.user_data.get("v2_pending_number")))
    prompt = (
        "أعد صياغة نص إعلان الزواج التالي بصياغة عربية سورية مرتبة ولطيفة. "
        "ممنوع إضافة أو حذف أي حقيقة أو رقم أو شرط؛ فقط تحسين الترتيب والوضوح. "
        "لا تذكر معلومات التواصل السرية. أعد النص فقط بدون مقدمة.\n\n" + source
    )
    try:
        response = await asyncio.to_thread(
            lambda: ai._get_client().models.generate_content(model=ai.model, contents=prompt)
        )
        improved = (response.text or "").strip()
        if improved:
            context.user_data["v2_improved_text"] = improved
            await update.callback_query.edit_message_text("🤖 تم تحسين صياغة الإعلان بدون إضافة معلومات جديدة:\n\n" + improved, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ اعتماد الصياغة", callback_data="admin:v2:add:use_improved"), InlineKeyboardButton("↩️ إبقاء الأصل", callback_data="admin:v2:add:preview")],
            ]))
        else:
            await update.callback_query.edit_message_text("⚠️ Gemini ما رجّع نصاً صالحاً.", reply_markup=_dashboard_keyboard())
    except Exception:
        await update.callback_query.edit_message_text("⚠️ تعذّر تحسين النص حالياً. البيانات الأصلية ما تغيرت.", reply_markup=_dashboard_keyboard())
    return ADMIN_V2_INPUT


async def _show_search_preview(update: Any, context: Any) -> int:
    query = context.user_data.get("v2_search_query") or {}
    filters = query["filters"]
    parts = []
    if filters.gender: parts.append("👩 عروس" if filters.gender == "female" else "🤵 عريس")
    if filters.residence: parts.append(f"📍 {filters.residence}")
    if filters.age_min is not None or filters.age_max is not None: parts.append(f"🎂 {filters.age_min or '—'} إلى {filters.age_max or '—'}")
    if filters.marital_status: parts.append(f"💍 {filters.marital_status}")
    if filters.occupation: parts.append(f"💼 {filters.occupation}")
    if filters.education: parts.append(f"📚 {filters.education}")
    if filters.children_min is not None or filters.children_max is not None: parts.append(f"👶 الأولاد: {filters.children_min if filters.children_min is not None else '—'} إلى {filters.children_max if filters.children_max is not None else '—'}")
    for key, label in (("status", "📊 الحالة"), ("publication_status", "📤 النشر"), ("text_query", "🔎 نص")):
        value = query.get(key)
        if value: parts.append(f"{label}: {value}")
    if not parts: parts.append("🔎 بحث عام")
    text = "🧠 فهمت البحث هيك:\n\n" + "\n".join(parts) + "\n\nهي المواصفات صحيحة؟"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تنفيذ البحث", callback_data="admin:v2:search:execute:0")],
        [InlineKeyboardButton("✏️ تعديل البحث", callback_data="admin:v2:search")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ])
    await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    return END


def _extract_admin_query(raw: str, ai_filters) -> dict[str, Any]:
    base = parse_search_text(raw)
    filters = merge_filters(base, filters_from_ai(ai_filters, raw)) if ai_filters else base
    normalized = raw.strip()
    number = None
    if normalized.isdigit(): number = int(normalized)
    else:
        match = re.search(r"(?:طلب|إعلان|اعلان)\s*#?\s*(\d+)", normalized, re.I)
        if match: number = int(match.group(1))
    status = None
    if re.search(r"محجوز", normalized): status = "reserved"
    elif re.search(r"معط(?:ل|ّل)", normalized): status = "inactive"
    elif re.search(r"متاح|فعال|فعّال", normalized): status = "active"
    elif re.search(r"مؤرشف|أرشيف", normalized): status = "archived"
    publication_status = None
    if re.search(r"جاهز(?:ة)? للنشر", normalized): publication_status = "ready"
    elif re.search(r"منشور|منشورة", normalized): publication_status = "published"
    elif re.search(r"غير منشور|غير منشورة|ألغي? النشر", normalized): publication_status = "unpublished"
    has_photo = True if re.search(r"مع صورة|فيه صورة|عليه صورة|لديه صورة", normalized) else False if re.search(r"بدون صورة|من دون صورة|ما عنده صورة", normalized) else None
    has_contact = True if re.search(r"مع رقم|رقم تواصل|مع واتساب|مع هاتف", normalized) else False if re.search(r"بدون رقم|من دون رقم|بلا رقم", normalized) else None
    height_min = height_max = weight_min = weight_max = None
    hm = re.search(r"طول(?:ه|ها)?\s*(?:بين|من)?\s*(\d{2,3})\s*(?:و|إلى|الى|لـ|-)?\s*(\d{2,3})?", normalized)
    if hm:
        height_min = int(hm.group(1)); height_max = int(hm.group(2)) if hm.group(2) else height_min
    wm = re.search(r"وزن(?:ه|ها)?\s*(?:بين|من)?\s*(\d{2,3})\s*(?:و|إلى|الى|لـ|-)?\s*(\d{2,3})?", normalized)
    if wm:
        weight_min = int(wm.group(1)); weight_max = int(wm.group(2)) if wm.group(2) else weight_min
    contact_query = None
    cm = re.search(r"(?:09\d{8,}|\+?963\s?9\d{8,})", normalized)
    if cm: contact_query = cm.group(0).replace(" ", "")
    name_query = None
    nm = re.search(r"(?:اسم(?:ها|ه)?|اسمه|اسمها)\s+([^،,\n]+)", normalized)
    if nm: name_query = nm.group(1).strip()
    text_query = None
    if not number and not contact_query and not name_query:
        stripped = re.sub(r"(?:بدي|بديلي|اعطيني|ورجيني|كل|كلو|طلبات|إعلانات|اعلانات|عرض|اعرض|من|بين|و|في|منه|ها|هم)\b", " ", normalized, flags=re.I)
        stripped = re.sub(r"\d+", " ", stripped)
        if len(stripped.strip()) >= 3 and not any((filters.gender, filters.residence, filters.age_min, filters.age_max, filters.marital_status, filters.occupation, filters.education, filters.children_min is not None, filters.children_max is not None)):
            text_query = stripped.strip()
    return {
        "filters": filters, "number": number, "status": status, "publication_status": publication_status,
        "has_photo": has_photo, "has_contact": has_contact, "height_min": height_min, "height_max": height_max,
        "weight_min": weight_min, "weight_max": weight_max, "contact_query": contact_query, "name_query": name_query,
        "text_query": text_query,
    }


def _query_admin_profiles(session, query: dict[str, Any], page: int, limit: int = 10) -> tuple[list[tuple[Profile, ProfileAdminMeta | None, ProfileContact | None]], bool]:
    q = query["filters"]
    stmt = select(Profile, ProfileAdminMeta, ProfileContact).outerjoin(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).outerjoin(ProfileContact, ProfileContact.profile_id == Profile.id)
    if q.gender: stmt = stmt.where(Profile.gender == q.gender)
    if q.residence: stmt = stmt.where(Profile.residence.ilike(f"%{q.residence.strip()}%"))
    if q.age_min is not None: stmt = stmt.where(Profile.age >= q.age_min)
    if q.age_max is not None: stmt = stmt.where(Profile.age <= q.age_max)
    if q.marital_status: stmt = stmt.where(Profile.marital_status.ilike(f"%{q.marital_status.strip()}%"))
    if q.occupation: stmt = stmt.where(Profile.occupation.ilike(f"%{q.occupation.strip()}%"))
    if q.education: stmt = stmt.where(Profile.education.ilike(f"%{q.education.strip()}%"))
    if q.children_min is not None: stmt = stmt.where(Profile.children_count >= q.children_min)
    if q.children_max is not None: stmt = stmt.where(Profile.children_count <= q.children_max)
    if query.get("status") == "archived": stmt = stmt.where(ProfileAdminMeta.archive_status == "archived")
    elif query.get("status"): stmt = stmt.where(Profile.status == query["status"])
    if query.get("publication_status"): stmt = stmt.where(ProfileAdminMeta.publication_status == query["publication_status"])
    if query.get("has_photo") is True: stmt = stmt.where(Profile.photo_file_id.is_not(None))
    if query.get("has_photo") is False: stmt = stmt.where(Profile.photo_file_id.is_(None))
    if query.get("has_contact") is True: stmt = stmt.where(or_(ProfileContact.phone.is_not(None), ProfileContact.whatsapp.is_not(None), ProfileContact.telegram_username.is_not(None)))
    if query.get("has_contact") is False: stmt = stmt.where(ProfileContact.phone.is_(None), ProfileContact.whatsapp.is_(None), ProfileContact.telegram_username.is_(None))
    if query.get("height_min") is not None: stmt = stmt.where(Profile.height >= query["height_min"])
    if query.get("height_max") is not None: stmt = stmt.where(Profile.height <= query["height_max"])
    if query.get("weight_min") is not None: stmt = stmt.where(Profile.weight >= query["weight_min"])
    if query.get("weight_max") is not None: stmt = stmt.where(Profile.weight <= query["weight_max"])
    if query.get("number") is not None: stmt = stmt.where(Profile.request_number == query["number"])
    if query.get("contact_query"):
        contact = query["contact_query"]
        stmt = stmt.where(or_(ProfileContact.phone.ilike(f"%{contact}%"), ProfileContact.whatsapp.ilike(f"%{contact}%")))
    if query.get("name_query"): stmt = stmt.where(Profile.name.ilike(f"%{query['name_query']}%"))
    if query.get("text_query"):
        term = f"%{query['text_query']}%"
        stmt = stmt.where(or_(Profile.name.ilike(term), Profile.residence.ilike(term), Profile.occupation.ilike(term), Profile.education.ilike(term), Profile.appearance.ilike(term), Profile.partner_requirements.ilike(term)))
    stmt = stmt.order_by(desc(Profile.created_at)).offset(page * limit).limit(limit + 1)
    rows = list(session.execute(stmt).all())
    return rows[:limit], len(rows) > limit


async def _run_search(update: Any, context: Any, page: int) -> int:
    query = context.user_data.get("v2_search_query")
    if not query:
        return END
    with _session(context) as session:
        rows, has_next = _query_admin_profiles(session, query, page)
    if not rows:
        await update.callback_query.edit_message_text("🔎 ما لقينا نتائج لهالبحث. جرّب توسع العمر أو السكن أو تشيل شرط.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 بحث جديد", callback_data="admin:v2:search")], [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]
        ]))
        return END
    text = f"🔎 النتائج — صفحة {page + 1}\n\n" + "\n".join(
        f"📌 طلب {p.request_number} — {p.name or 'بدون اسم'} — {p.age} سنة — {p.residence} — {'🔒 محجوز' if p.status == 'reserved' else '⛔ معطّل' if p.status == 'inactive' else '✅ متاح'}"
        for p, _, _ in rows
    )
    buttons = [[InlineKeyboardButton(f"📌 تفاصيل {p.request_number}", callback_data=f"admin:v2:profile:{p.request_number}")] for p, _, _ in rows]
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin:v2:search:execute:{page-1}"))
    if has_next: nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin:v2:search:execute:{page+1}"))
    if nav: buttons.append(nav)
    buttons += [[InlineKeyboardButton("🔄 بحث جديد", callback_data="admin:v2:search")], [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return END


async def _show_reservations(update: Any, context: Any, page: int) -> int:
    with _session(context) as session:
        expire_reservations(session)
        stmt = select(Profile, ProfileAdminMeta).join(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).where(Profile.status == "reserved").order_by(desc(ProfileAdminMeta.reserved_at)).offset(page*10).limit(11)
        rows = list(session.execute(stmt).all())
        has_next = len(rows) > 10
        rows = rows[:10]
    if not rows:
        await update.callback_query.edit_message_text("🔒 ما في عروض محجوزة حالياً.", reply_markup=_dashboard_keyboard())
        return END
    text = "🔒 الحجوزات\n\n"
    buttons=[]
    for profile, meta in rows:
        expiry = "بدون انتهاء"
        if meta.reservation_expires_at:
            expiry = meta.reservation_expires_at.strftime("%Y-%m-%d %H:%M")
        text += f"📌 {profile.request_number} — {profile.name or 'بدون اسم'} — {profile.age} سنة — {profile.residence}\n⏰ {expiry}\n💬 {meta.reservation_reason or 'بدون سبب'}\n\n"
        buttons.append([InlineKeyboardButton(f"📌 عرض {profile.request_number}", callback_data=f"admin:v2:profile:{profile.request_number}"), InlineKeyboardButton("🔓 فك", callback_data=f"admin:v2:unreserve:{profile.request_number}")])
    nav=[]
    if page>0: nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin:v2:reservations:{page-1}"))
    if has_next: nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin:v2:reservations:{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return END


async def _start_reserve(update: Any, context: Any, number: int) -> int:
    context.user_data["v2_flow"] = "reserve_reason"
    context.user_data["v2_reserve_number"] = number
    await update.callback_query.edit_message_text("🔒 مدة الحجز؟", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("7 أيام", callback_data=f"admin:v2:reserve:duration:{number}:7"), InlineKeyboardButton("14 يوم", callback_data=f"admin:v2:reserve:duration:{number}:14")],
        [InlineKeyboardButton("30 يوم", callback_data=f"admin:v2:reserve:duration:{number}:30"), InlineKeyboardButton("بدون مدة", callback_data=f"admin:v2:reserve:duration:{number}:0")],
        [InlineKeyboardButton("⬅️ الإعلان", callback_data=f"admin:v2:profile:{number}")],
    ]))
    return ADMIN_V2_INPUT


async def _finish_reserve(update: Any, context: Any, reason: str | None = None) -> int:
    number = int(context.user_data.get("v2_reserve_number"))
    days = int(context.user_data.get("v2_reserve_days", 0))
    with _session(context) as session:
        profile = ProfileRepository(session).get(number)
        if profile is None or profile.status == "inactive":
            await update.effective_message.reply_text("❌ ما قدرنا نحجز هالإعلان.", reply_markup=_dashboard_keyboard())
            return END
        profile.status = "reserved"
        meta = get_profile_meta(session, profile.id, create=True)
        now = datetime.now(timezone.utc)
        meta.reserved_at = now
        meta.reservation_expires_at = now + timedelta(days=days) if days else None
        meta.reservation_reason = reason
        log_admin_action(session, int(update.effective_user.id), "profile_reserve", "profile", number, {"days": days, "reason": reason})
        session.commit()
    context.user_data.clear()
    await update.effective_message.reply_text(f"🔒 تم حجز الإعلان رقم {number}.", reply_markup=_dashboard_keyboard())
    return END


async def _archive(update: Any, context: Any, number: int) -> int:
    if not _require_role(update, context, {"owner", "manager"}):
        await update.callback_query.answer("❌ هالعملية للمديرين فقط.", show_alert=True)
        return END
    with _session(context) as session:
        profile = ProfileRepository(session).get(number)
        if profile is None:
            await update.callback_query.edit_message_text("❌ ما لقينا الإعلان.", reply_markup=_dashboard_keyboard()); return END
        profile.status = "inactive"
        meta = get_profile_meta(session, profile.id, create=True)
        meta.archive_status = "archived"; meta.archived_at = datetime.now(timezone.utc); meta.publication_status = "unpublished"
        log_admin_action(session, int(update.effective_user.id), "profile_archive", "profile", number)
        session.commit()
    await update.callback_query.edit_message_text(f"📦 تم أرشفة الإعلان رقم {number}.\n\nالبيانات ما انحذفت.", reply_markup=_dashboard_keyboard())
    return END


async def _reactivate(update: Any, context: Any, number: int) -> int:
    if not _require_role(update, context, {"owner", "manager"}):
        await update.callback_query.answer("❌ هالعملية للمديرين فقط.", show_alert=True); return END
    with _session(context) as session:
        profile = ProfileRepository(session).get(number)
        if profile is None:
            await update.callback_query.edit_message_text("❌ ما لقينا الإعلان.", reply_markup=_dashboard_keyboard()); return END
        profile.status = "active"
        meta = get_profile_meta(session, profile.id, create=True)
        meta.archive_status = "active"; meta.archived_at = None
        meta.publication_status = "ready" if meta.quality_score >= 75 else "review"
        log_admin_action(session, int(update.effective_user.id), "profile_reactivate", "profile", number)
        session.commit()
    await update.callback_query.edit_message_text(f"♻️ تم إعادة تفعيل الإعلان رقم {number}.", reply_markup=_dashboard_keyboard())
    return END


async def _show_orders(update: Any, context: Any, page: int, filter_name: str) -> int:
    with _session(context) as session:
        stmt = select(Order, OrderAdminMeta).outerjoin(OrderAdminMeta, OrderAdminMeta.order_id == Order.id).order_by(desc(Order.created_at)).offset(page*10).limit(11)
        if filter_name == "pending": stmt = stmt.where(Order.status.in_(["pending_payment", "pending_review"]))
        elif filter_name == "paid": stmt = stmt.where(Order.status == "paid")
        elif filter_name == "completed": stmt = stmt.where(OrderAdminMeta.contact_status == "completed")
        rows = list(session.execute(stmt).all()); has_next = len(rows) > 10; rows = rows[:10]
        for order, meta in rows:
            get_order_meta(session, order.id, create=True)
        session.commit()
    if not rows:
        await update.callback_query.edit_message_text("💳 ما في طلبات بهالقسم.", reply_markup=_dashboard_keyboard()); return END
    text="💳 طلبات التواصل\n\n"; buttons=[]
    for order, meta in rows:
        payment_label = "✅ مدفوع" if order.status == "paid" else "🟠 بانتظار الدفع" if order.status in {"pending_payment", "pending_review"} else "❌ مرفوض"
        contact_label = {"new":"🆕 جديد","contacted":"📞 تم التواصل","opened":"🤝 مفتوح","completed":"✅ مكتمل","cancelled":"❌ ملغى"}.get(meta.contact_status if meta else "new", "🆕 جديد")
        text += f"📌 طلب {order.order_number} — إعلان {order.profile.request_number if order.profile else '?'}\n{payment_label} — {contact_label}\n📱 {order.whatsapp or 'بدون واتساب'}\n\n"
        buttons.append([InlineKeyboardButton(f"🔎 {order.order_number}", callback_data=f"admin:v2:order:view:{order.order_number}"), InlineKeyboardButton("✅", callback_data=f"admin:v2:order:confirm:{order.order_number}"), InlineKeyboardButton("❌", callback_data=f"admin:v2:order:reject:{order.order_number}")])
    buttons.append([InlineKeyboardButton("🟢 المدفوعة", callback_data="admin:v2:orders:0:paid"), InlineKeyboardButton("✅ المكتملة", callback_data="admin:v2:orders:0:completed")])
    nav=[]
    if page>0: nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin:v2:orders:{page-1}:{filter_name}"))
    if has_next: nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin:v2:orders:{page+1}:{filter_name}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons)); return END


async def _view_order(update: Any, context: Any, number: int) -> int:
    with _session(context) as session:
        order = OrderRepository(session).get(number)
        if order is None:
            await update.callback_query.edit_message_text("❌ ما لقينا طلب التواصل.", reply_markup=_dashboard_keyboard()); return END
        meta = get_order_meta(session, order.id, create=True)
        profile = ProfileRepository(session).get_with_contact(order.profile.request_number)
        session.commit()
    payment_state = meta.payment_status; contact_state = meta.contact_status
    text = (
        f"💳 طلب التواصل رقم {number}\n\n"
        f"🧾 الإعلان: {order.profile.request_number if order.profile else '—'}\n"
        f"🆔 Telegram ID: {order.user_telegram_id}\n"
        f"📱 WhatsApp: {order.whatsapp or '—'}\n"
        f"💵 المبلغ: {order.amount_usd} USD\n"
        f"💳 الدفع: {payment_state}\n"
        f"🤝 التواصل: {contact_state}\n\n"
        + (format_admin_profile(profile) if profile else "❌ بيانات الإعلان غير موجودة")
    )
    await update.callback_query.edit_message_text(text, reply_markup=_order_actions(order, payment_state, contact_state)); return END


async def _order_transition(update: Any, context: Any, number: int, transition: str) -> int:
    with _session(context) as session:
        order = OrderRepository(session).get(number)
        if order is None:
            await update.callback_query.edit_message_text("❌ ما لقينا الطلب.", reply_markup=_dashboard_keyboard()); return END
        meta = get_order_meta(session, order.id, create=True)
        now = datetime.now(timezone.utc)
        if transition == "confirm": meta.payment_status = "paid"; order.status = "paid"
        elif transition == "reject": meta.payment_status = "rejected"; meta.contact_status = "cancelled"; order.status = "rejected"; order.notes = "إلغاء يدوي من الأدمن"
        elif transition == "contacted": meta.contact_status = "contacted"; meta.contacted_at = now
        elif transition == "opened": meta.contact_status = "opened"
        elif transition == "complete": meta.contact_status = "completed"; meta.completed_at = now
        log_admin_action(session, int(update.effective_user.id), f"order_{transition}", "order", number)
        user_id = order.user_telegram_id
        session.commit()
    messages = {
        "confirm": f"✅ تم تأكيد الدفع لطلب التواصل رقم {number}.",
        "reject": f"❌ تم إلغاء طلب التواصل رقم {number}.",
        "contacted": f"📞 تم تسجيل التواصل مع العميل لطلب {number}.",
        "opened": f"🤝 تم فتح التواصل لطلب {number}.",
        "complete": f"✅ تم إغلاق طلب التواصل رقم {number} كمكتمل.",
    }
    try:
        await context.application.bot.send_message(user_id, messages[transition])
    except Exception:
        pass
    await update.callback_query.edit_message_text(messages[transition], reply_markup=_dashboard_keyboard()); return END


async def _delete_profile(update: Any, context: Any, number: int) -> int:
    if not _require_role(update, context, {"owner", "manager"}):
        await update.callback_query.answer("❌ الحذف النهائي للمديرين فقط.", show_alert=True); return END
    await update.callback_query.edit_message_text(
        f"⚠️ حذف نهائي للإعلان {number}\n\nسيتم حذف الإعلان وطلبات التواصل المرتبطة به. قبل التنفيذ رح تنعمل نسخة احتياطية تلقائياً.\n\nاكتب عبارة **حذف نهائي** لتأكيد العملية.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=f"admin:v2:profile:{number}")], [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]]),
    )
    context.user_data["v2_flow"] = "delete_profile_confirm"; context.user_data["v2_delete_number"] = number
    return ADMIN_V2_INPUT


async def _delete_profile_confirm(update: Any, context: Any, text: str) -> int:
    if text.strip() != "حذف نهائي":
        await update.effective_message.reply_text("❌ ما تم الحذف. اكتب بالضبط: حذف نهائي", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
    number = int(context.user_data["v2_delete_number"])
    with _session(context) as session:
        create_backup(session, int(update.effective_user.id), f"قبل حذف الإعلان {number}")
        count = ProfileRepository(session).delete_requests([number])
        log_admin_action(session, int(update.effective_user.id), "profile_delete_permanent", "profile", number, {"deleted": count})
        session.commit()
    context.user_data.clear()
    await update.effective_message.reply_text(f"✅ تم حذف الإعلان {number} نهائياً بعد إنشاء نسخة احتياطية.", reply_markup=_dashboard_keyboard()); return END


async def _delete_order(update: Any, context: Any, number: int) -> int:
    if not _require_role(update, context, {"owner", "manager"}):
        await update.callback_query.answer("❌ حذف الطلبات للمديرين فقط.", show_alert=True); return END
    context.user_data["v2_flow"] = "delete_order_confirm"; context.user_data["v2_delete_order_number"] = number
    await update.callback_query.edit_message_text(f"⚠️ رح ينحذف طلب التواصل {number} نهائياً.\n\nاكتب **حذف الطلب** للتأكيد.", parse_mode="Markdown", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT


async def _delete_order_confirm(update: Any, context: Any, text: str) -> int:
    if text.strip() != "حذف الطلب":
        await update.effective_message.reply_text("❌ اكتب بالضبط: حذف الطلب", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
    number = int(context.user_data["v2_delete_order_number"])
    with _session(context) as session:
        create_backup(session, int(update.effective_user.id), f"قبل حذف طلب التواصل {number}")
        deleted = OrderRepository(session).delete_order(number)
        log_admin_action(session, int(update.effective_user.id), "order_delete", "order", number, {"deleted": deleted})
        session.commit()
    context.user_data.clear(); await update.effective_message.reply_text("✅ تم حذف الطلب بعد إنشاء نسخة احتياطية.", reply_markup=_dashboard_keyboard()); return END


async def _show_reports(update: Any, context: Any) -> int:
    with _session(context) as session:
        data = metrics(session)
    p, o = data["profiles"], data["orders"]
    text = (
        "📊 تقارير لقاء ونصيب\n\n"
        "👥 الإعلانات\n"
        f"اليوم: {p['today']} | الأسبوع: {p['week']} | الشهر: {p['month']}\n"
        f"👩 العرائس: {p['female']} | 🤵 العرسان: {p['male']}\n\n"
        "💳 الطلبات\n"
        f"اليوم: {o['today']} | الأسبوع: {o['week']} | الشهر: {o['month']}\n"
        f"🟠 معلقة: {o['pending']} | ✅ مدفوعة: {o['paid']} | ❌ مرفوضة: {o['rejected']}\n"
        f"📞 تم التواصل: {o['contacted']} | ✅ مكتملة: {o['completed']}\n"
        f"📈 التحويل إلى مكتمل: {o['conversion']}%\n\n"
        "📍 أكثر أماكن السكن:\n" + "\n".join(f"{i+1}. {name} — {count}" for i, (name, count) in enumerate(data["top_residences"]))
    )
    await update.callback_query.edit_message_text(text, reply_markup=_back_keyboard()); return END


async def _show_backups(update: Any, context: Any) -> int:
    with _session(context) as session:
        rows = list_backups(session, 10)
    text = "💾 النسخ الاحتياطية\n\n"
    if not rows: text += "ما في نسخ احتياطية حالياً."
    else:
        text += "\n".join(f"💾 #{b.id} — {b.created_at.strftime('%Y-%m-%d %H:%M')} — {b.reason} — أدمن {b.created_by_admin_id}" for b in rows)
    buttons = [[InlineKeyboardButton("💾 إنشاء نسخة الآن", callback_data="admin:v2:backup:create")], [InlineKeyboardButton("📥 تنزيل آخر نسخة", callback_data="admin:v2:backup:download:last")], [InlineKeyboardButton("♻️ استعادة نسخة", callback_data="admin:v2:backup:restore")], [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons)); return END


async def _create_backup(update: Any, context: Any) -> int:
    if not _require_role(update, context, {"owner", "manager"}):
        await update.callback_query.answer("❌ النسخ الاحتياطية للمديرين فقط.", show_alert=True); return END
    with _session(context) as session:
        row = create_backup(session, int(update.effective_user.id), "نسخة يدوية من الأدمن"); session.commit(); backup_id = row.id
        payload = row.snapshot_json.encode("utf-8")
    await update.callback_query.message.reply_document(BufferedInputFile(payload, filename=f"naseb-backup-{backup_id}.json"), caption=f"💾 نسخة احتياطية #{backup_id}")
    await update.callback_query.edit_message_text(f"✅ تم إنشاء النسخة الاحتياطية #{backup_id}.", reply_markup=_dashboard_keyboard()); return END


async def _download_last_backup(update: Any, context: Any) -> int:
    with _session(context) as session:
        row = session.scalar(select(AdminBackup).order_by(desc(AdminBackup.created_at)).limit(1))
    if row is None:
        await update.callback_query.edit_message_text("❌ ما في نسخة احتياطية.", reply_markup=_dashboard_keyboard()); return END
    await update.callback_query.message.reply_document(BufferedInputFile(row.snapshot_json.encode("utf-8"), filename=f"naseb-backup-{row.id}.json"), caption=f"💾 النسخة #{row.id}")
    await update.callback_query.edit_message_text("✅ انبعتت آخر نسخة احتياطية.", reply_markup=_dashboard_keyboard()); return END


async def _start_restore(update: Any, context: Any) -> int:
    if not _require_role(update, context, {"owner"}):
        await update.callback_query.answer("❌ استعادة النسخ للمالك فقط.", show_alert=True); return END
    with _session(context) as session:
        rows = list_backups(session, 10)
    if not rows:
        await update.callback_query.edit_message_text("❌ ما في نسخة للاستعادة.", reply_markup=_dashboard_keyboard()); return END
    buttons = [[InlineKeyboardButton(f"♻️ استعادة #{b.id} — {b.created_at.strftime('%Y-%m-%d %H:%M')}", callback_data=f"admin:v2:backup:restore:{b.id}")] for b in rows]
    buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin:v2:backups")])
    await update.callback_query.edit_message_text("♻️ اختر النسخة التي تريد استعادتها.\n\nسيتم أولاً إنشاء نسخة أمان من الوضع الحالي.", reply_markup=InlineKeyboardMarkup(buttons)); return END


async def _confirm_restore(update: Any, context: Any, backup_id: int) -> int:
    if not _require_role(update, context, {"owner"}):
        await update.callback_query.answer("❌ الاستعادة للمالك فقط.", show_alert=True); return END
    with _session(context) as session:
        row = session.get(AdminBackup, backup_id)
    if row is None:
        await update.callback_query.edit_message_text("❌ النسخة غير موجودة.", reply_markup=_dashboard_keyboard()); return END
    context.user_data["v2_flow"] = "restore_confirm"; context.user_data["v2_restore_id"] = backup_id
    await update.callback_query.edit_message_text(f"⚠️ استعادة النسخة #{backup_id}\n\nسيتم استبدال بيانات الإعلانات والطلبات الحالية بمحتوى النسخة بعد إنشاء نسخة أمان.\n\nاكتب **استعادة النسخة** للتأكيد.", parse_mode="Markdown", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT


async def _restore_confirm(update: Any, context: Any, text: str) -> int:
    if text.strip() != "استعادة النسخة":
        await update.effective_message.reply_text("❌ لم تتم الاستعادة. اكتب: استعادة النسخة", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
    backup_id = int(context.user_data["v2_restore_id"])
    with _session(context) as session:
        target = session.get(AdminBackup, backup_id)
        if target is None: raise RuntimeError("النسخة غير موجودة")
        create_backup(session, int(update.effective_user.id), f"قبل استعادة النسخة {backup_id}")
        result = restore_snapshot(session, target.snapshot_json)
        log_admin_action(session, int(update.effective_user.id), "backup_restore", "backup", backup_id, result)
        session.commit()
    context.user_data.clear(); await update.effective_message.reply_text(f"✅ تمت استعادة النسخة #{backup_id}.\n\n👥 الإعلانات: {result['profiles']}\n💳 الطلبات: {result['orders']}", reply_markup=_dashboard_keyboard()); return END


async def _show_audit(update: Any, context: Any) -> int:
    with _session(context) as session:
        rows = list_audit_logs(session, 25)
    text = "🧾 سجل العمليات\n\n" + ("لا يوجد سجل بعد." if not rows else "\n".join(f"{r.created_at.strftime('%m-%d %H:%M')} — 👤 {r.admin_user_id} — {r.action}{f' — {r.entity_type} {r.entity_number}' if r.entity_number else ''}" for r in rows))
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث", callback_data="admin:v2:audit")], [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]])); return END


async def _show_settings(update: Any, context: Any) -> int:
    settings = _settings(context)
    with _session(context) as session:
        amount = service_price(session); method = payment_method(session)
    access = getattr(settings, "admin_access", None)
    role_text = "غير مفصّلة" if access is None else "\n".join(f"{uid}: {access.role_for(uid)}" for uid in sorted(settings.admin_user_ids))
    text = (
        "⚙️ إعدادات الأدمن\n\n"
        f"💵 سعر الخدمة: {amount} USD\n"
        f"💳 طريقة الدفع: {method}\n"
        f"🤖 Gemini: {'✅ مهيأ' if settings.ai_api_key else '❌ غير مهيأ'}\n"
        f"🗄️ قاعدة البيانات: {'✅ متصلة' if settings.database_url else '❌ غير مهيأة'}\n\n"
        "👑 الصلاحيات:\n" + role_text
    )
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 تغيير السعر", callback_data="admin:v2:settings:price"), InlineKeyboardButton("💳 تغيير طريقة الدفع", callback_data="admin:v2:settings:method")],
        [InlineKeyboardButton("👑 الصلاحيات", callback_data="admin:v2:settings:roles")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ])); return END


async def _settings_input(update: Any, context: Any, text: str) -> int:
    flow = context.user_data.get("v2_flow")
    try:
        if flow == "settings_price":
            value = Decimal(text.strip()).quantize(Decimal("0.01"))
            if value < 0 or value > Decimal("10000"): raise InvalidOperation
            with _session(context) as session:
                set_setting(session, "service_amount_usd", str(value), int(update.effective_user.id)); session.commit()
            context.user_data.clear(); await update.effective_message.reply_text("✅ تم تحديث سعر الخدمة.", reply_markup=_dashboard_keyboard()); return END
        if flow == "settings_method":
            value = text.strip()
            if not value: raise ValueError
            with _session(context) as session:
                set_setting(session, "payment_method", value, int(update.effective_user.id)); session.commit()
            context.user_data.clear(); await update.effective_message.reply_text("✅ تم تحديث طريقة الدفع.", reply_markup=_dashboard_keyboard()); return END
    except (InvalidOperation, ValueError):
        await update.effective_message.reply_text("❌ القيمة غير صالحة. جرّب من جديد.", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
    return END


async def admin_callback(update: Any, context: Any) -> int:
    _remember_admin(context, update)
    if not _is_admin(update, context):
        query = update.callback_query
        await query.answer("❌ ما عندك صلاحية لهالعملية.", show_alert=True); return END
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("admin:v2:"):
        if data == "admin:v2:dashboard": return await _dashboard(update, context)
        if data == "admin:v2:add": return await _start_add(update, context)
        if data == "admin:v2:add:cancel": context.user_data.clear(); await query.edit_message_text("✅ تم إلغاء الإضافة.", reply_markup=_dashboard_keyboard()); return END
        if data == "admin:v2:add:save": return await _save_add(update, context)
        if data == "admin:v2:add:edit": context.user_data["v2_flow"] = "add_edit"; await query.edit_message_text("✏️ ابعت التعديلات سطر بسطر مثل:\nالعمر=25\nمكان السكن=دمشق\nواتساب=09xxxxxxxx", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        if data == "admin:v2:add:duplicate:continue": context.user_data["v2_duplicate_ack"] = True; return await _show_add_preview(update, context)
        if data == "admin:v2:add:duplicate:cancel": context.user_data.clear(); await query.edit_message_text("✅ تم إلغاء الإضافة لأن الإعلان مشابه لإعلان موجود.", reply_markup=_dashboard_keyboard()); return END
        if data == "admin:v2:add:duplicates":
            duplicates = context.user_data.get("v2_duplicate_matches") or []
            text = "🔍 فحص التكرار\n\n" + ("ما في تشابهات قوية." if not duplicates else "\n".join(f"📌 {d.request_number} — {d.name or 'بدون اسم'} — تشابه {d.score}% — {', '.join(d.reasons)}" for d in duplicates))
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ المعاينة", callback_data="admin:v2:add:preview")]])); return ADMIN_V2_INPUT
        if data == "admin:v2:add:improve": return await _improve_draft(update, context)
        if data == "admin:v2:add:preview": return await _show_add_preview(update, context)
        if data == "admin:v2:add:use_improved":
            improved = context.user_data.get("v2_improved_text")
            if improved: context.user_data["v2_publish_text"] = improved
            return await _show_add_preview(update, context)
        if data == "admin:v2:add:publish_text":
            draft = context.user_data.get("v2_draft")
            if draft: await query.edit_message_text(format_marriage_post(dict(draft.public_data, request_number=context.user_data.get("v2_pending_number"))), reply_markup=_back_keyboard())
            return ADMIN_V2_INPUT
        if data == "admin:v2:add:ready":
            quality = context.user_data.get("v2_quality")
            if quality and quality.ready:
                context.user_data["v2_ready"] = True; await query.edit_message_text("🟢 الإعلان صار جاهز للنشر حسب فحص البيانات.", reply_markup=_back_keyboard())
            else:
                await query.edit_message_text("⚠️ الإعلان بعده بحاجة لإكمال البيانات الأساسية.", reply_markup=_back_keyboard())
            return ADMIN_V2_INPUT

        if data == "admin:v2:search":
            context.user_data["v2_flow"] = "search_input"; await query.edit_message_text("🔎 اكتب طلب البحث بطريقتك. مثال:\n\nكل البنات من دمشق بين 22 و28 عزباء، أو الإعلان 154، أو كل المعطلة.", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        if data.startswith("admin:v2:search:execute:"):
            page = int(data.rsplit(":",1)[1]); return await _run_search(update, context, page)

        if data.startswith("admin:v2:profiles:"):
            parts = data.split(":"); return await _show_profiles(update, context, int(parts[3]), parts[4])
        if data.startswith("admin:v2:profile:"): return await _show_profile(update, context, int(data.rsplit(":",1)[1]))
        if data.startswith("admin:v2:edit:") and ":editfield:" not in data:
            number = int(data.rsplit(":",1)[1]); context.user_data["v2_edit_number"] = number; await query.edit_message_text("✏️ اختار الحقل الذي تريد تعديله:", reply_markup=_edit_fields_keyboard(number)); return END
        if data.startswith("admin:v2:editfield:"):
            parts=data.split(":"); number=int(parts[3]); field=parts[4]; context.user_data.update({"v2_flow":"edit_field","v2_edit_number":number,"v2_edit_field":field})
            if field == "photo": await query.edit_message_text("📷 ابعت الصورة الجديدة الآن.", reply_markup=_back_keyboard())
            else: await query.edit_message_text(f"✏️ اكتب القيمة الجديدة للحقل: {field}", reply_markup=_back_keyboard())
            return ADMIN_V2_INPUT

        if data.startswith("admin:v2:archive:"): return await _archive(update, context, int(data.rsplit(":",1)[1]))
        if data.startswith("admin:v2:reactivate:"): return await _reactivate(update, context, int(data.rsplit(":",1)[1]))
        if data.startswith("admin:v2:reserve:") and ":duration:" not in data: return await _start_reserve(update, context, int(data.rsplit(":",1)[1]))
        if data.startswith("admin:v2:reserve:duration:"):
            parts=data.split(":"); number=int(parts[4]); days=int(parts[5]); context.user_data.update({"v2_flow":"reserve_reason","v2_reserve_number":number,"v2_reserve_days":days}); await query.edit_message_text("💬 سبب الحجز؟ اكتب السبب أو اضغط بدون سبب.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بدون سبب", callback_data="admin:v2:reserve:reason:none")],[InlineKeyboardButton("⬅️ رجوع", callback_data=f"admin:v2:profile:{number}")]])); return ADMIN_V2_INPUT
        if data == "admin:v2:reserve:reason:none": return await _finish_reserve(update, context, None)
        if data.startswith("admin:v2:unreserve:"):
            number=int(data.rsplit(":",1)[1])
            with _session(context) as session:
                profile=ProfileRepository(session).get(number)
                if profile: profile.status="active"; meta=get_profile_meta(session, profile.id, create=True); meta.reserved_at=None; meta.reservation_expires_at=None; meta.reservation_reason=None; log_admin_action(session,int(update.effective_user.id),"profile_unreserve","profile",number); session.commit()
            await query.edit_message_text("🔓 تم إلغاء الحجز.", reply_markup=_dashboard_keyboard()); return END

        if data == "admin:v2:reservations:0": return await _show_reservations(update, context, 0)
        if data.startswith("admin:v2:reservations:"): return await _show_reservations(update, context, int(data.rsplit(":",1)[1]))

        if data == "admin:v2:orders:0:pending": return await _show_orders(update, context, 0, "pending")
        if data.startswith("admin:v2:orders:"):
            parts=data.split(":"); return await _show_orders(update, context, int(parts[3]), parts[4])
        if data.startswith("admin:v2:order:view:"): return await _view_order(update, context, int(data.rsplit(":",1)[1]))
        for transition in ("confirm","reject","contacted","opened","complete"):
            prefix=f"admin:v2:order:{transition}:"
            if data.startswith(prefix): return await _order_transition(update, context, int(data[len(prefix):]), transition)
        if data.startswith("admin:v2:order:delete:"): return await _delete_order(update, context, int(data.rsplit(":",1)[1]))

        if data == "admin:v2:reports": return await _show_reports(update, context)
        if data == "admin:v2:backups": return await _show_backups(update, context)
        if data == "admin:v2:backup:create": return await _create_backup(update, context)
        if data == "admin:v2:backup:download:last": return await _download_last_backup(update, context)
        if data == "admin:v2:backup:restore": return await _start_restore(update, context)
        if data.startswith("admin:v2:backup:restore:"): return await _confirm_restore(update, context, int(data.rsplit(":",1)[1]))
        if data == "admin:v2:audit": return await _show_audit(update, context)
        if data == "admin:v2:settings": return await _show_settings(update, context)
        if data == "admin:v2:settings:price":
            if not _require_role(update, context, {"owner","manager"}): await query.answer("❌ للمديرين فقط.", show_alert=True); return END
            context.user_data["v2_flow"]="settings_price"; await query.edit_message_text("💵 اكتب السعر بالدولار، مثال: 5 أو 5.00", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        if data == "admin:v2:settings:method":
            if not _require_role(update, context, {"owner","manager"}): await query.answer("❌ للمديرين فقط.", show_alert=True); return END
            context.user_data["v2_flow"]="settings_method"; await query.edit_message_text("💳 اكتب طريقة الدفع الجديدة.", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        if data == "admin:v2:settings:roles":
            await query.edit_message_text("👑 الصلاحيات تُدار من متغيرات Render الاختيارية:\n\nADMIN_OWNER_IDS\nADMIN_MANAGER_IDS\nADMIN_VIEWER_IDS\n\nوالقائمة القديمة ADMIN_USER_IDS تبقى مدعومة للتوافق.", reply_markup=_back_keyboard()); return END
        if data.startswith("admin:v2:publish:text:"):
            number=int(data.rsplit(":",1)[1])
            with _session(context) as session: profile=ProfileRepository(session).get_public(number)
            if profile is None: await query.edit_message_text("❌ ما لقينا الإعلان.", reply_markup=_dashboard_keyboard()); return END
            await query.edit_message_text(format_marriage_post(profile), reply_markup=_back_keyboard()); return END
        if data.startswith("admin:v2:publish:") and not data.startswith("admin:v2:publish:text:"):
            number=int(data.rsplit(":",1)[1])
            with _session(context) as session:
                profile=ProfileRepository(session).get(number)
                if profile is None: await query.edit_message_text("❌ ما لقينا الإعلان.", reply_markup=_dashboard_keyboard()); return END
                meta=get_profile_meta(session,profile.id,True); meta.publication_status="published"; meta.published_at=datetime.now(timezone.utc); log_admin_action(session,int(update.effective_user.id),"profile_publish","profile",number); session.commit()
            await query.edit_message_text("📤 تم اعتماد الإعلان كمنشور.", reply_markup=_dashboard_keyboard()); return END
        if data.startswith("admin:v2:unpublish:"):
            number=int(data.rsplit(":",1)[1])
            with _session(context) as session:
                profile=ProfileRepository(session).get(number); meta=get_profile_meta(session,profile.id,True) if profile else None
                if meta: meta.publication_status="unpublished"; log_admin_action(session,int(update.effective_user.id),"profile_unpublish","profile",number); session.commit()
            await query.edit_message_text("↩️ تم إلغاء حالة النشر.", reply_markup=_dashboard_keyboard()); return END
        if data.startswith("admin:v2:delete:"): return await _delete_profile(update, context, int(data.rsplit(":",1)[1]))

    # Protect legacy destructive shortcuts and upgrade old order/profile controls.
    if data == "admin:menu": return await _dashboard(update, context)
    if data in {"admin:list", "admin:stats", "admin:backup", "admin:reservations", "admin:orders", "admin:search", "admin:add", "admin:edit", "admin:disable"}:
        mapped = {
            "admin:list": "admin:v2:profiles:0:all", "admin:stats":"admin:v2:reports", "admin:backup":"admin:v2:backups", "admin:reservations":"admin:v2:reservations:0", "admin:orders":"admin:v2:orders:0:pending", "admin:search":"admin:v2:search", "admin:add":"admin:v2:add",
        }.get(data)
        if mapped:
            query.data = mapped
            return await admin_callback(update, context)
    if data.startswith("admin:profile:"):
        query.data = f"admin:v2:profile:{data.rsplit(':',1)[1]}"; return await admin_callback(update, context)
    if data.startswith("admin:reserve:"):
        query.data = f"admin:v2:reserve:{data.rsplit(':',1)[1]}"; return await admin_callback(update, context)
    if data.startswith("admin:unreserve:"):
        query.data = f"admin:v2:unreserve:{data.rsplit(':',1)[1]}"; return await admin_callback(update, context)
    if data == "admin:delete":
        await query.edit_message_text("🗃️ إدارة الإزالة\n\nالإزالة العادية أصبحت أرشفة للحفاظ على البيانات. للحذف النهائي، افتح الإعلان واستخدم خيار حذف نهائي.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 إدارة الإعلانات", callback_data="admin:v2:profiles:0:all")],[InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]])); return END
    if data.startswith("admin:delete:one:"):
        return await _archive(update, context, int(data.rsplit(":",1)[1]))
    if data.startswith("admin:delete:"):
        await query.answer("ℹ️ الحذف القديم تم استبداله بالأرشفة والحذف النهائي المؤكد.", show_alert=True); return END
    return await legacy.admin_callback(update, context)


async def admin_text(update: Any, context: Any) -> int:
    _remember_admin(context, update)
    if not _is_admin(update, context):
        await update.effective_message.reply_text("❌ ما عندك صلاحية لهالعملية."); return END
    flow=context.user_data.get("v2_flow"); text=(update.effective_message.text or "").strip()
    if flow == "add_raw": return await _parse_add(update, context, text)
    if flow == "add_edit":
        draft=context.user_data.get("v2_draft")
        if draft is None: await update.effective_message.reply_text("❌ ما في مسودة.", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        context.user_data["v2_draft"]=apply_text_edits(draft,text); context.user_data["v2_quality"]=score_profile(context.user_data["v2_draft"]); return await _show_add_preview(update,context)
    if flow == "search_input":
        ai=context.application.bot_data["ai_service"]; ai_filters=None
        if ai.is_configured:
            try: ai_filters=await ai.parse_search_filters(text)
            except Exception: ai_filters=None
        context.user_data["v2_search_query"]=_extract_admin_query(text,ai_filters)
        return await _show_search_preview(update,context)
    if flow == "edit_field":
        number=int(context.user_data["v2_edit_number"]); field=context.user_data["v2_edit_field"]
        if field == "photo": return ADMIN_V2_INPUT
        value=text
        if field in {"age","children_count"}:
            try: value=int(value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩","0123456789")))
            except ValueError: await update.effective_message.reply_text("❌ لازم رقم صحيح.", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        if field in {"height","weight"}:
            try: value=float(value.replace(",","."))
            except ValueError: await update.effective_message.reply_text("❌ لازم رقم صحيح.", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        with _session(context) as session:
            ProfileRepository(session).update(number,{field:value}); log_admin_action(session,int(update.effective_user.id),"profile_field_edit","profile",number,{"field":field}); session.commit()
        context.user_data.clear(); await update.effective_message.reply_text("✅ تم تعديل الحقل.", reply_markup=_dashboard_keyboard()); return END
    if flow == "reserve_reason": return await _finish_reserve(update,context,text)
    if flow == "delete_profile_confirm": return await _delete_profile_confirm(update,context,text)
    if flow == "delete_order_confirm": return await _delete_order_confirm(update,context,text)
    if flow == "restore_confirm": return await _restore_confirm(update,context,text)
    if flow in {"settings_price","settings_method"}: return await _settings_input(update,context,text)
    return await legacy.admin_text(update, context)


async def admin_photo(update: Any, context: Any) -> int:
    _remember_admin(context, update)
    if not _is_admin(update, context):
        await update.effective_message.reply_text("❌ ما عندك صلاحية لهالعملية."); return END
    flow=context.user_data.get("v2_flow")
    if flow == "add_raw":
        caption=(update.effective_message.caption or "").strip()
        if not caption: await update.effective_message.reply_text("✍️ حط نص الإعلان كـCaption للصورة.", reply_markup=_back_keyboard()); return ADMIN_V2_INPUT
        return await _parse_add(update,context,caption,photo_file_id=update.effective_message.photo[-1].file_id)
    if flow == "edit_field" and context.user_data.get("v2_edit_field") == "photo":
        number=int(context.user_data["v2_edit_number"]); file_id=update.effective_message.photo[-1].file_id
        with _session(context) as session:
            ProfileRepository(session).update(number,{"photo_file_id":file_id}); log_admin_action(session,int(update.effective_user.id),"profile_photo_edit","profile",number); session.commit()
        context.user_data.clear(); await update.effective_message.reply_text("✅ تم تحديث الصورة.", reply_markup=_dashboard_keyboard()); return END
    return await legacy.admin_photo(update, context)
