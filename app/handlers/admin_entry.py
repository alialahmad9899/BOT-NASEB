"""Top-level Admin V2 callback/text guard.

This adapter protects read-only roles, keeps legacy callbacks alive, and routes
all destructive operations through the Admin V2 safety rules.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select, text
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.database.admin_models import AdminBackup, ProfileAdminMeta
from app.database.models import Order
from app.database.repositories import OrderRepository, ProfileRepository
from app.handlers import admin_router
from app.services.admin_access import effective_admin_ids, effective_role
from app.services.admin_meta import create_backup, get_admin_roles, get_order_meta, get_profile_meta, list_audit_logs, log_admin_action, metrics, payment_method, service_price, save_admin_roles, ADMIN_ROLES_SETTING_KEY, PRIMARY_ADMIN_ID
from app.services.profile_quality import score_profile
from app.services.profiles import ProfileDraft, format_marriage_post

ADMIN_V2_INPUT = admin_router.ADMIN_V2_INPUT
END = ConversationHandler.END


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _role(context: Any, user_id: int) -> str | None:
    return effective_role(context, int(user_id))


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
        "admin:v2:unreserve", "admin:v2:reservation:extend", "admin:v2:delete",
        "admin:v2:unpublish", "admin:v2:order:confirm", "admin:v2:order:reject", "admin:v2:order:contacted",
        "admin:v2:order:opened", "admin:v2:order:complete", "admin:v2:order:delete", "admin:v2:backup:create",
        "admin:v2:backup:download", "admin:order:confirm", "admin:order:reject", "admin:order:contacted", "admin:order:opened", "admin:order:complete", "admin:order:delete",
        "admin:v2:backup:restore", "admin:v2:settings:price", "admin:v2:settings:method", "admin:v2:danger",
        "admin:orders:delete:pending",
    )
    return any(data.startswith(prefix) for prefix in write_prefixes)


def _publish_view_keyboard(number: int, publication_status: str) -> InlineKeyboardMarkup:
    if publication_status == "published":
        action = InlineKeyboardButton("↩️ إلغاء النشر", callback_data=f"admin:v2:unpublish:{number}")
    else:
        action = InlineKeyboardButton("📣 نشر الإعلان", callback_data=f"admin:v2:publish:{number}")
    return InlineKeyboardMarkup([
        [action],
        [InlineKeyboardButton("⬅️ الإعلان", callback_data=f"admin:v2:profile:{number}")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ])


async def _show_publish_view(update: Any, context: Any, number: int) -> int:
    with _session(context) as session:
        profile = ProfileRepository(session).get_with_contact(number)
        if profile is None:
            await update.callback_query.edit_message_text("❌ ما لقينا الإعلان.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
            return END
        meta = get_profile_meta(session, int(profile["id"]), create=True)
        publication_status = meta.publication_status
        session.commit()
    await update.callback_query.edit_message_text(
        format_marriage_post(profile),
        reply_markup=_publish_view_keyboard(number, publication_status),
    )
    return END


async def _warn_before_incomplete_save(update: Any, context: Any) -> int:
    draft: ProfileDraft | None = context.user_data.get("v2_draft")
    if draft is None:
        return await admin_router.admin_callback(update, context)
    quality = score_profile(draft)
    if not quality.missing_fields:
        return await admin_router.admin_callback(update, context)
    missing = "، ".join(quality.missing_fields)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ متابعة وحفظ رغم النقص", callback_data="admin:v2:add:save:force")],
        [InlineKeyboardButton("✏️ تعديل البيانات", callback_data="admin:v2:add:edit")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:add:cancel")],
    ])
    await update.callback_query.edit_message_text(
        "⚠️ في معلومات ناقصة بالإعلان:\n\n"
        f"{missing}\n\n"
        "المعلومات الناقصة ما رح تمنع الحفظ، لكن الأفضل تكملها قبل النشر.\n\n"
        "شو بتحب تعمل؟",
        reply_markup=keyboard,
    )
    return ADMIN_V2_INPUT


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
    with _session(context) as session:
        roles_map = get_admin_roles(session, settings)
    roles = "\n".join(f"{uid}: {_role_label(role)}" for uid, role in sorted(roles_map.items()))
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


async def _incomplete_profiles_screen(update: Any, context: Any) -> int:
    with _session(context) as session:
        stmt = (
            select(ProfileAdminMeta).where(ProfileAdminMeta.publication_status == "review")
            .order_by(desc(ProfileAdminMeta.updated_at)).limit(15)
        )
        metas = list(session.scalars(stmt).all())
        rows = []
        for meta in metas:
            profile = session.get(__import__("app.database.models", fromlist=["Profile"]).Profile, meta.profile_id)
            if profile:
                rows.append((profile, meta))
    if not rows:
        await update.callback_query.edit_message_text(
            "⚠️ بحاجة لاستكمال\n\n✅ ما في إعلانات معلّقة للمراجعة حالياً.",
            reply_markup=admin_router.admin_v2._dashboard_keyboard(),
        )
        return END
    text_body = "⚠️ إعلانات بحاجة لاستكمال\n\n"
    buttons = []
    for profile, meta in rows:
        text_body += f"📌 {profile.request_number} — {profile.name or 'بدون اسم'} — {profile.age or '—'} سنة — {profile.residence or '—'}\n⭐ الجودة: {meta.quality_score}/100\n\n"
        buttons.append([InlineKeyboardButton(f"📌 فتح {profile.request_number}", callback_data=f"admin:v2:profile:{profile.request_number}")])
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    await update.callback_query.edit_message_text(text_body, reply_markup=InlineKeyboardMarkup(buttons))
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
        log_admin_action(session, int(update.effective_user.id), "reservation_extend", "profile", number, {"days": days})
        session.commit()
    await update.callback_query.edit_message_text(f"✅ تم تعديل مدة حجز الإعلان {number}.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
    return END


async def _bulk_delete_pending_orders_confirm(update: Any, context: Any) -> int:
    if not _manager(update, context):
        await update.callback_query.answer("❌ هالعملية للمديرين فقط.", show_alert=True)
        return END
    with _session(context) as session:
        pending = len(OrderRepository(session).list_pending(limit=50))
    if pending == 0:
        await update.callback_query.edit_message_text("💳 ما في طلبات معلّقة.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
        return END
    context.user_data["v2_flow"] = "danger_pending_orders"
    await update.callback_query.edit_message_text(
        f"⚠️ رح ينحذف {pending} طلب تواصل معلّق نهائياً.\n\n"
        "رح نعمل نسخة احتياطية تلقائياً قبل الحذف.\n\n"
        "اكتب **حذف كل الطلبات المعلّقة** للتأكيد.",
        parse_mode="Markdown",
        reply_markup=admin_router.admin_v2._back_keyboard(),
    )
    return ADMIN_V2_INPUT


async def _bulk_delete_pending_orders_execute(update: Any, context: Any) -> int:
    if not _manager(update, context):
        await update.callback_query.answer("❌ للمديرين فقط.", show_alert=True)
        return END
    with _session(context) as session:
        create_backup(session, int(update.effective_user.id), "قبل حذف كل طلبات التواصل المعلّقة")
        count = OrderRepository(session).delete_pending()
        log_admin_action(session, int(update.effective_user.id), "bulk_pending_order_delete", "order", None, {"count": count})
        session.commit()
    context.user_data.clear()
    await update.callback_query.edit_message_text(
        f"✅ تم حذف {count} طلبات تواصل معلّقة بعد إنشاء نسخة احتياطية.",
        reply_markup=admin_router.admin_v2._dashboard_keyboard(),
    )
    return END


async def _bulk_delete_pending_orders(update: Any, context: Any) -> int:
    if (update.effective_message.text or "").strip() != "حذف كل الطلبات المعلّقة":
        await update.effective_message.reply_text("❌ لم يتم الحذف.", reply_markup=admin_router.admin_v2._back_keyboard())
        return ADMIN_V2_INPUT
    if not _manager(update, context):
        await update.effective_message.reply_text("❌ للمديرين فقط.")
        return END
    with _session(context) as session:
        create_backup(session, int(update.effective_user.id), "قبل حذف كل طلبات التواصل المعلّقة")
        count = OrderRepository(session).delete_pending()
        log_admin_action(session, int(update.effective_user.id), "bulk_pending_order_delete", "order", None, {"count": count})
        session.commit()
    context.user_data.clear()
    await update.effective_message.reply_text(f"✅ تم حذف {count} طلبات معلّقة بعد إنشاء نسخة احتياطية.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
    return END



def _role_label(role: str) -> str:
    return {"owner": "👑 مالك رئيسي", "manager": "👔 موظف", "viewer": "👀 مشاهدة فقط"}.get(role, role)


async def _roles_manage_screen(update: Any, context: Any) -> int:
    user = update.effective_user
    if user is None or not _owner(update, context):
        await update.callback_query.answer("❌ إدارة الأدمنات للمالك الرئيسي فقط.", show_alert=True)
        return END
    settings = context.application.bot_data["settings"]
    with _session(context) as session:
        roles = get_admin_roles(session, settings)
    lines = [
        f"👤 {uid} — {_role_label(role)}"
        + (" 🔒" if uid == PRIMARY_ADMIN_ID else "")
        for uid, role in sorted(roles.items())
    ]
    rows = [
        [InlineKeyboardButton("➕ إضافة أدمن", callback_data="admin:v2:roles:add")],
        [InlineKeyboardButton("📢 إشعار لبقية الأدمن", callback_data="admin:v2:roles:notify")],
    ]
    for uid, role in sorted(roles.items()):
        if uid == PRIMARY_ADMIN_ID:
            continue
        rows.append([InlineKeyboardButton(f"🗑️ إزالة {uid} ({_role_label(role)})", callback_data=f"admin:v2:roles:remove:{uid}")])
    rows.append([InlineKeyboardButton("⬅️ إعدادات الصلاحيات", callback_data="admin:v2:section:settings:roles")])
    await update.callback_query.edit_message_text(
        "👑 إدارة الأدمنات\n\n"
        + ("\n".join(lines) if lines else "لا يوجد أدمنات.")
        + "\n\n🔒 المالك الرئيسي لا يمكن إزالة صلاحياته من داخل البوت.",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return END


async def _start_admin_add(update: Any, context: Any) -> int:
    if not _owner(update, context):
        await update.callback_query.answer("❌ إضافة الأدمنات للمالك الرئيسي فقط.", show_alert=True)
        return END
    context.user_data["v2_flow"] = "admin_roles_add_id"
    await update.callback_query.edit_message_text(
        "➕ إضافة أدمن\n\n"
        "ابعت Telegram User ID للشخص اللي بدك تضيفه.\n"
        "بعدها منختار نوع الصلاحية.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:roles:manage")],
            [InlineKeyboardButton("⬅️ إعدادات الصلاحيات", callback_data="admin:v2:section:settings:roles")],
        ]),
    )
    return ADMIN_V2_INPUT


async def _save_admin_role(update: Any, context: Any, role: str) -> int:
    if not _owner(update, context):
        await update.callback_query.answer("❌ إدارة الأدمنات للمالك الرئيسي فقط.", show_alert=True)
        return END
    target_id = context.user_data.get("v2_new_admin_id")
    if not target_id or role not in {"manager", "viewer"}:
        context.user_data.clear()
        await update.callback_query.edit_message_text("❌ تعذرت إضافة الأدمن. بلّش العملية من جديد.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
        return END
    target_id = int(target_id)
    if target_id == PRIMARY_ADMIN_ID:
        context.user_data.clear()
        await update.callback_query.edit_message_text("⚠️ هذا الحساب هو المالك الرئيسي أصلاً.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
        return END

    settings = context.application.bot_data["settings"]
    with _session(context) as session:
        roles = get_admin_roles(session, settings)
        previous = roles.get(target_id)
        roles[target_id] = role
        save_admin_roles(session, roles, int(update.effective_user.id))
        log_admin_action(
            session,
            int(update.effective_user.id),
            "admin_role_add" if previous is None else "admin_role_change",
            "admin",
            target_id,
            {"role": role, "previous": previous},
        )
        session.commit()

    context.user_data.clear()
    role_label = _role_label(role)
    await update.callback_query.edit_message_text(
        f"✅ تم إضافة/تحديث الأدمن {target_id}.\n\n"
        f"👤 الصلاحية: {role_label}",
        reply_markup=admin_router.admin_v2._dashboard_keyboard(),
    )
    await _notify_admin_role_change(context, int(update.effective_user.id), target_id, "add", role)
    return END


async def _confirm_remove_admin(update: Any, context: Any, target_id: int) -> int:
    if not _owner(update, context):
        await update.callback_query.answer("❌ إزالة الأدمنات للمالك الرئيسي فقط.", show_alert=True)
        return END
    if target_id == PRIMARY_ADMIN_ID:
        await update.callback_query.answer("🔒 لا يمكن إزالة المالك الرئيسي.", show_alert=True)
        return END
    with _session(context) as session:
        roles = get_admin_roles(session, context.application.bot_data["settings"])
    role = roles.get(target_id)
    if role is None:
        await update.callback_query.edit_message_text("❌ هذا الحساب مو مسجل كأدمن.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
        return END
    context.user_data["v2_remove_admin_id"] = target_id
    await update.callback_query.edit_message_text(
        f"⚠️ إزالة صلاحية الأدمن\n\n"
        f"🆔 Telegram ID: {target_id}\n"
        f"👤 الصلاحية الحالية: {_role_label(role)}\n\n"
        "متأكد بدك تشيل عنه صلاحية الأدمن؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ نعم، أزل الصلاحية", callback_data=f"admin:v2:roles:remove:confirm:{target_id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:roles:manage")],
        ]),
    )
    return END


async def _remove_admin(update: Any, context: Any, target_id: int) -> int:
    if not _owner(update, context):
        await update.callback_query.answer("❌ إزالة الأدمنات للمالك الرئيسي فقط.", show_alert=True)
        return END
    if target_id == PRIMARY_ADMIN_ID:
        await update.callback_query.answer("🔒 لا يمكن إزالة المالك الرئيسي.", show_alert=True)
        return END
    settings = context.application.bot_data["settings"]
    with _session(context) as session:
        roles = get_admin_roles(session, settings)
        previous = roles.pop(target_id, None)
        if previous is None:
            await update.callback_query.edit_message_text("❌ هذا الحساب لم يعد مسجلاً كأدمن.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
            return END
        save_admin_roles(session, roles, int(update.effective_user.id))
        log_admin_action(
            session,
            int(update.effective_user.id),
            "admin_role_remove",
            "admin",
            target_id,
            {"previous": previous},
        )
        session.commit()

    context.user_data.clear()
    await update.callback_query.edit_message_text(
        f"✅ تمت إزالة صلاحية الأدمن عن {target_id}.",
        reply_markup=admin_router.admin_v2._dashboard_keyboard(),
    )
    await _notify_admin_role_change(context, int(update.effective_user.id), target_id, "remove", previous)
    return END


async def _start_admin_notify(update: Any, context: Any) -> int:
    if not _owner(update, context):
        await update.callback_query.answer("❌ إرسال الإشعارات للمالك الرئيسي فقط.", show_alert=True)
        return END
    context.user_data["v2_flow"] = "admin_staff_notify"
    await update.callback_query.edit_message_text(
        "📢 إشعار للموظفين

"
        "اكتب نص الرسالة اللي بدك توصل للموظفين.
"
        "رح تنبعت لكل حسابات الموظفين المسجلين كـ«موظف».",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:roles:manage")],
            [InlineKeyboardButton("⬅️ إدارة الأدمنات", callback_data="admin:v2:roles:manage")],
        ]),
    )
    return ADMIN_V2_INPUT


async def _send_staff_notification(update: Any, context: Any, message: str) -> int:
    if not _owner(update, context):
        context.user_data.clear()
        await update.effective_message.reply_text(
            "❌ إرسال الإشعارات للمالك الرئيسي فقط.",
            reply_markup=admin_router.admin_v2._dashboard_keyboard(),
        )
        return END
    message = message.strip()
    if not message:
        await update.effective_message.reply_text(
            "❌ اكتب نص الإشعار أولاً.",
            reply_markup=_back_keyboard(),
        )
        return ADMIN_V2_INPUT

    settings = context.application.bot_data["settings"]
    with _session(context) as session:
        roles = get_admin_roles(session, settings)
        recipients = sorted(uid for uid in roles if uid != int(update.effective_user.id))
        log_admin_action(
            session,
            int(update.effective_user.id),
            "admin_staff_broadcast",
            "admin",
            None,
            {"recipients": recipients},
        )
        session.commit()

    delivered = 0
    failed = 0
    for admin_id in recipients:
        try:
            await context.application.bot.send_message(
                admin_id,
                "📢 إشعار من المالك الرئيسي في «لقاء ونصيب»\n\n" + message,
            )
            delivered += 1
        except Exception:
            failed += 1

    context.user_data.clear()
    await update.effective_message.reply_text(
        f"✅ تم إرسال الإشعار إلى {delivered} أدمن."
        + (f"\n⚠️ تعذر الإرسال إلى {failed} أدمن." if failed else ""),
        reply_markup=admin_router.admin_v2._dashboard_keyboard(),
    )
    return END


async def _notify_admin_role_change(context: Any, actor_id: int, target_id: int, action: str, role: str) -> None:
    active_admins = set(effective_admin_ids(context))
    if action == "add":
        message_target = (
            "👑 إشعار صلاحيات\n\n"
            "تمت إضافتك كأدمن في «لقاء ونصيب».\n"
            f"🆔 Telegram ID: {target_id}\n"
            f"👤 الصلاحية: {_role_label(role)}\n\n"
            "يمكنك استخدام لوحة الأدمن حسب صلاحياتك."
        )
        try:
            await context.application.bot.send_message(target_id, message_target)
        except Exception:
            pass
        message_others = (
            "🔔 إشعار إداري\n\n"
            "تمت إضافة أدمن جديد إلى «لقاء ونصيب».\n"
            f"🆔 Telegram ID: {target_id}\n"
            f"👤 الصلاحية: {_role_label(role)}"
        )
        recipients = active_admins - {actor_id, target_id}
    else:
        message_target = (
            "🔔 إشعار صلاحيات\n\n"
            "تمت إزالة صلاحية الأدمن عن حسابك في «لقاء ونصيب».\n"
            "إذا كان هذا بالخطأ، تواصل مع المالك الرئيسي."
        )
        try:
            await context.application.bot.send_message(target_id, message_target)
        except Exception:
            pass
        message_others = (
            "🔔 إشعار إداري\n\n"
            "تمت إزالة صلاحية أدمن من أحد الحسابات.\n"
            f"🆔 Telegram ID: {target_id}\n"
            f"👤 الصلاحية السابقة: {_role_label(role)}"
        )
        recipients = active_admins - {actor_id}
    for admin_id in recipients:
        try:
            await context.application.bot.send_message(admin_id, message_others)
        except Exception:
            pass


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

    if data == "admin:v2:roles:manage":
        return await _roles_manage_screen(update, context)
    if data == "admin:v2:roles:add":
        return await _start_admin_add(update, context)
    if data == "admin:v2:roles:notify":
        return await _start_admin_notify(update, context)
    if data == "admin:v2:roles:add:manager":
        return await _save_admin_role(update, context, "manager")
    if data == "admin:v2:roles:add:viewer":
        return await _save_admin_role(update, context, "viewer")
    remove_confirm = re.fullmatch(r"admin:v2:roles:remove:confirm:(\d+)", data)
    if remove_confirm:
        return await _remove_admin(update, context, int(remove_confirm.group(1)))
    remove_match = re.fullmatch(r"admin:v2:roles:remove:(\d+)", data)
    if remove_match:
        return await _confirm_remove_admin(update, context, int(remove_match.group(1)))

    publish_match = re.fullmatch(r"admin:v2:publish:text:(\d+)", data)
    if publish_match:
        return await _show_publish_view(update, context, int(publish_match.group(1)))

    if data == "admin:v2:add:save":
        return await _warn_before_incomplete_save(update, context)
    if data == "admin:v2:add:save:force":
        query = update.callback_query
        original = query.data
        query.data = "admin:v2:add:save"
        try:
            return await admin_router.admin_callback(update, context)
        finally:
            query.data = original

    if data == "admin:v2:audit":
        return await _audit_screen(update, context)
    if data == "admin:v2:settings":
        return await _settings_screen(update, context)
    if data == "admin:v2:profiles:0:incomplete":
        return await _incomplete_profiles_screen(update, context)
    match = re.fullmatch(r"admin:v2:reservation:extend:(\d+):(\d+)", data)
    if match:
        return await _extend_reservation(update, context, int(match.group(1)), int(match.group(2)))
    if data == "admin:orders:delete:pending":
        return await _bulk_delete_pending_orders_confirm(update, context)
    if data == "admin:orders:delete:pending:confirm":
        return await _bulk_delete_pending_orders_execute(update, context)
    return await admin_router.admin_callback(update, context)


async def admin_text(update: Any, context: Any) -> int:
    user = update.effective_user
    if user is None or _role(context, int(user.id)) is None:
        await update.effective_message.reply_text("❌ ما عندك صلاحية لهالعملية.")
        return END
    flow = context.user_data.get("v2_flow")
    if flow == "admin_staff_notify":
        return await _send_staff_notification(update, context, (update.effective_message.text or "").strip())

    if flow == "admin_roles_add_id":
        if not _owner(update, context):
            context.user_data.clear()
            await update.effective_message.reply_text("❌ إدارة الأدمنات للمالك الرئيسي فقط.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
            return END
        raw_id = (update.effective_message.text or "").strip()
        if not raw_id.isdigit() or int(raw_id) <= 0:
            await update.effective_message.reply_text(
                "❌ Telegram User ID لازم يكون رقماً صحيحاً موجباً.",
                reply_markup=_back_keyboard(),
            )
            return ADMIN_V2_INPUT
        target_id = int(raw_id)
        if target_id == PRIMARY_ADMIN_ID:
            context.user_data.clear()
            await update.effective_message.reply_text(
                "⚠️ هذا الحساب هو المالك الرئيسي أصلاً.",
                reply_markup=admin_router.admin_v2._dashboard_keyboard(),
            )
            return END
        with _session(context) as session:
            roles = get_admin_roles(session, context.application.bot_data["settings"])
            current = roles.get(target_id)
        context.user_data["v2_new_admin_id"] = target_id
        current_label = _role_label(current) if current else "غير مضاف"
        await update.effective_message.reply_text(
            f"🆔 Telegram ID: {target_id}\n"
            f"👤 الحالة الحالية: {current_label}\n\n"
            "اختار نوع الصلاحية:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👔 موظف", callback_data="admin:v2:roles:add:manager")],
                [InlineKeyboardButton("👀 مشاهدة فقط", callback_data="admin:v2:roles:add:viewer")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="admin:v2:roles:manage")],
            ]),
        )
        return ADMIN_V2_INPUT

    if _role(context, int(user.id)) == "viewer" and flow in {
        "add_raw", "add_edit", "edit_field", "reserve_reason", "delete_profile_confirm", "delete_order_confirm",
        "danger_selected", "danger_selected_confirm", "danger_all", "restore_confirm", "settings_price", "settings_method",
        "archive_custom_reason", "danger_pending_orders",
    }:
        await update.effective_message.reply_text("👀 حساب المشاهدة للعرض فقط.", reply_markup=admin_router.admin_v2._dashboard_keyboard())
        return END
    if flow == "danger_pending_orders":
        return await _bulk_delete_pending_orders(update, context)
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
