"""Top-level Admin V2 callback/text guard.

This small adapter protects read-only roles and fixes routing edge cases before
delegating the full feature set to `admin_router`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select, text
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.database.admin_models import AdminBackup, ProfileAdminMeta
from app.database.models import Profile
from app.database.repositories import OrderRepository, ProfileRepository
from app.handlers import admin_router
from app.services.admin_meta import get_order_meta, get_profile_meta, list_audit_logs, metrics, payment_method, service_price

ADMIN_V2_INPUT = admin_router.ADMIN_V2_INPUT
END = ConversationHandler.END


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _role(context: Any, user_id: int) -> str | None:
    access = getattr(context.application.bot_data["settings"], "admin_access", None)
    return access.role_for(user_id) if access else ("owner" if user_id in context.application.bot_data["settings"].admin_user_ids else None)


def _manager(update: Any, context: Any) -> bool:
    user = update.effective_user
    return bool(user and _role(context, int(user.id)) in {"owner", "manager"})


def _owner(update: Any, context: Any) -> bool:
    user = update.effective_user
    return bool(user and _role(context, int(user.id)) == "owner")


def _viewer_blocked(data: str) -> bool:
    write_prefixes = (
        "admin:add", "admin:edit", "admin:disable", "admin:delete", "admin:reserve", "admin:unreserve",
        "admin:v2:add", "admin:v2:edit", "admin:v2:archive", "admin:v2:reactivate", "admin:v2:reserve",
        "admin:v2:unreserve", "admin:v2:reservation:extend", "admin:v2:delete", "admin:v2:publish",
        "admin:v2:unpublish", "admin:v2:order:confirm", "admin:v2:order:reject", "admin:v2:order:contacted",
        "admin:v2:order:opened", "admin:v2:order:complete", "admin:v2:order:delete", "admin:v2:backup:create",
        "admin:v2:backup:restore", "admin:v2:settings:price", "admin:v2:settings:method", "admin:v2:danger",
    )
    return any(data.startswith(prefix) for prefix in write_prefixes)


async def _audit_screen(update: Any, context: Any) -> int:
    with _session(context) as session:
        rows = list_audit_logs(session, 25)
    body = "🧾 سجل العمليات\n\n" + ("لا يوجد سجل بعد." if not rows else "\n".join(
        f"{r.created_at.strftime('%Y-%m-%d %H:%M')} — 👤 {r.admin_user_id} — {r.action}"
        f"{f' — {r.entity_type} {r.entity_number}' if r.entity_number else ''}"
        for r in rows
    ))
    await update.callback_query.edit_message_text(body, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 فلترة السجل", callback_data="admin:v2:audit:filter")],
        [InlineKeyboardButton("🔄 تحديث", callback_data="admin:v2:audit")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ]))
    return END


async def _settings_screen(update: Any, context: Any) -> int:
    with _session(context) as session:
        try:
            session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        amount = service_price(session)
        method = payment_method(session)
    settings = context.application.bot_data["settings"]
    access = getattr(settings, "admin_access", None)
    roles = "\n".join(f"{uid}: {access.role_for(uid)}" for uid in sorted(settings.admin_user_ids)) if access else "غير مفصلة"
    await update.callback_query.edit_message_text(
        "⚙️ إعدادات الأدمن\n\n"
        f"💵 سعر الخدمة: {amount:g} USD\n"
        f"💳 طريقة الدفع: {method}\n"
        f"🤖 Gemini: {'✅ مهيأ' if settings.ai_api_key else '❌ غير مهيأ'}\n"
        f"🗄️ قاعدة البيانات: {'✅ سليمة' if db_ok else '❌ يوجد خلل'}\n\n"
        "👑 الصلاحيات:\n" + roles,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💵 تغيير السعر", callback_data="admin:v2:settings:price"), InlineKeyboardButton("💳 تغيير طريقة الدفع", callback_data="admin:v2:settings:method")],
            [InlineKeyboardButton("👑 الصلاحيات", callback_data="admin:v2:settings:roles")],
            [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
        ]),
    )
    return END


async def _extend_reservation(update: Any, context: Any, number: int, days: int) -> int:
    if not _manager(update, context):
        await update.callback_query.answer("❌ هالعملية للمديرين فقط.", show_alert=True)
        return END
    with _session(context) as session:
        profile = ProfileRepository(session).get(number)
        if profile is None or profile.status != "reserved":
            await update.callback_query.edit_message_text("❌ الإعلان مو محجوز حالياً.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
            return END
        meta = get_profile_meta(session, profile.id, True)
        now = datetime.now(timezone.utc)
        if days == 0:
            meta.reservation_expires_at = None
        else:
            base = meta.reservation_expires_at if meta.reservation_expires_at and meta.reservation_expires_at > now else now
            meta.reservation_expires_at = base + timedelta(days=days)
        session.commit()
    await update.callback_query.edit_message_text(f"✅ تم تعديل مدة حجز الإعلان {number}.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
    return END


async def admin_callback(update: Any, context: Any) -> int:
    user = update.effective_user
    if user is None:
        return END
    context.user_data["v2_admin_user_id"] = int(user.id)
    data = update.callback_query.data or ""
    role = _role(context, int(user.id))
    if role is None:
        await update.callback_query.answer("❌ ما عندك صلاحية لهالعملية.", show_alert=True)
        return END
    if role == "viewer" and _viewer_blocked(data):
        await update.callback_query.answer("👀 حساب المشاهدة لا يملك صلاحية التعديل أو الحذف.", show_alert=True)
        return END
    if data == "admin:v2:audit":
        return await _audit_screen(update, context)
    if data == "admin:v2:settings":
        return await _settings_screen(update, context)
    match = re.fullmatch(r"admin:v2:reservation:extend:(\d+):(\d+)", data)
    if match:
        return await _extend_reservation(update, context, int(match.group(1)), int(match.group(2)))
    # Delegation preserves all existing callbacks and the legacy aliases.
    return await admin_router.admin_callback(update, context)


async def admin_text(update: Any, context: Any) -> int:
    user = update.effective_user
    if user is None or _role(context, int(user.id)) is None:
        await update.effective_message.reply_text("❌ ما عندك صلاحية لهالعملية.")
        return END
    if _role(context, int(user.id)) == "viewer" and context.user_data.get("v2_flow") in {
        "add_raw", "add_edit", "edit_field", "reserve_reason", "delete_profile_confirm", "delete_order_confirm",
        "danger_selected", "danger_selected_confirm", "danger_all", "restore_confirm", "settings_price", "settings_method",
        "archive_custom_reason",
    }:
        await update.effective_message.reply_text("👀 حساب المشاهدة للعرض فقط.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
        return END
    return await admin_router.admin_text(update, context)


async def admin_photo(update: Any, context: Any) -> int:
    user = update.effective_user
    if user is None or _role(context, int(user.id)) is None:
        await update.effective_message.reply_text("❌ ما عندك صلاحية لهالعملية.")
        return END
    if _role(context, int(user.id)) == "viewer":
        await update.effective_message.reply_text("👀 حساب المشاهدة للعرض فقط.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
        return END
    return await admin_router.admin_photo(update, context)
