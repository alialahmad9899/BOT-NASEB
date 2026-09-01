"""Final Admin V2 safety/router layer.

Adds destructive-operation guards, archive reasons, reservation extension,
audit filtering and real database health checks while delegating the main UX
implementation to `admin_v2`.
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
from app.database.repositories import ProfileRepository
from app.handlers import admin_v2
from app.services.admin_meta import create_backup, get_profile_meta, list_audit_logs, log_admin_action, metrics

END = ConversationHandler.END
ADMIN_V2_INPUT = admin_v2.ADMIN_V2_INPUT


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _role(context: Any, user_id: int) -> str | None:
    access = getattr(context.application.bot_data["settings"], "admin_access", None)
    if access is not None:
        return access.role_for(user_id)
    return "owner" if user_id in context.application.bot_data["settings"].admin_user_ids else None


def _manager(update: Any, context: Any) -> bool:
    user = update.effective_user
    return bool(user and _role(context, int(user.id)) in {"owner", "manager"})


def _owner(update: Any, context: Any) -> bool:
    user = update.effective_user
    return bool(user and _role(context, int(user.id)) == "owner")


def _dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 الإعلانات والبحث", callback_data="admin:v2:section:ads")],
        [InlineKeyboardButton("➕ إضافة إعلان", callback_data="admin:v2:add")],
        [InlineKeyboardButton("💳 الطلبات والتواصل", callback_data="admin:v2:section:orders")],
        [InlineKeyboardButton("🔒 الحجوزات", callback_data="admin:v2:section:reservations")],
        [InlineKeyboardButton("📣 النشر والمحتوى", callback_data="admin:v2:section:publishing")],
        [InlineKeyboardButton("📊 التقارير والمتابعة", callback_data="admin:v2:section:reports")],
        [InlineKeyboardButton("🛡️ الأمان والنسخ", callback_data="admin:v2:section:security")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin:v2:section:settings")],
    ])


def _section_keyboard(title: str, rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    rows = list(rows)
    rows.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    return InlineKeyboardMarkup(rows)


def _dashboard_text(snapshot: dict[str, Any]) -> str:
    p = snapshot["profiles"]
    o = snapshot["orders"]
    return (
        "🔐 لوحة تحكم لقاء ونصيب\n\n"
        "📊 الحالة الآن\n"
        f"✅ متاحة: {p['active']}   🔒 محجوزة: {p['reserved']}   ⛔ معطلة: {p['inactive']}\n"
        f"🗃️ مؤرشفة: {p['archived']}\n"
        f"💳 طلبات متابعة: {o['pending']}   💰 مدفوعة: {o['paid']}   ✅ مكتملة: {o['completed']}\n\n"
        "اختار القسم اللي بدك تديره:"
    )


def _ads_section_keyboard() -> InlineKeyboardMarkup:
    return _section_keyboard("الإعلانات والبحث", [
        [InlineKeyboardButton("🔎 البحث الذكي", callback_data="admin:v2:search")],
        [InlineKeyboardButton("📋 كل الإعلانات", callback_data="admin:v2:profiles:0:all")],
        [InlineKeyboardButton("👩 حسب الجنس", callback_data="admin:v2:section:ads:gender"), InlineKeyboardButton("📊 حسب الحالة", callback_data="admin:v2:section:ads:status")],
        [InlineKeyboardButton("⭐ الجودة والنشر", callback_data="admin:v2:section:ads:quality")],
    ])


def _orders_section_keyboard() -> InlineKeyboardMarkup:
    return _section_keyboard("الطلبات والتواصل", [
        [InlineKeyboardButton("🆕 الجديدة", callback_data="admin:v2:orders:0:pending")],
        [InlineKeyboardButton("💰 المدفوعة", callback_data="admin:v2:orders:0:paid"), InlineKeyboardButton("✅ المكتملة", callback_data="admin:v2:orders:0:completed")],
        [InlineKeyboardButton("📋 كل الطلبات", callback_data="admin:v2:orders:0:all")],
        [InlineKeyboardButton("🛑 منطقة العمليات الخطرة", callback_data="admin:v2:danger")],
    ])


def _settings_section_keyboard() -> InlineKeyboardMarkup:
    return _section_keyboard("الإعدادات", [
        [InlineKeyboardButton("💵 الدفع والأسعار", callback_data="admin:v2:section:settings:payments")],
        [InlineKeyboardButton("👑 الأدمن والصلاحيات", callback_data="admin:v2:section:settings:roles")],
        [InlineKeyboardButton("🤖 الذكاء الاصطناعي", callback_data="admin:v2:section:settings:ai")],
        [InlineKeyboardButton("🔧 حالة النظام", callback_data="admin:v2:section:settings:status")],
    ])


def _archive_keyboard(number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💍 تمت الزيجة", callback_data=f"admin:v2:archive:reason:{number}:تمت الزيجة")],
        [InlineKeyboardButton("👤 طلب صاحب الإعلان", callback_data=f"admin:v2:archive:reason:{number}:طلب صاحب الإعلان")],
        [InlineKeyboardButton("🕰️ إعلان قديم", callback_data=f"admin:v2:archive:reason:{number}:إعلان قديم")],
        [InlineKeyboardButton("📦 بدون سبب", callback_data=f"admin:v2:archive:reason:{number}:بدون سبب")],
        [InlineKeyboardButton("✍️ سبب آخر", callback_data=f"admin:v2:archive:custom:{number}")],
        [InlineKeyboardButton("⬅️ الإعلان", callback_data=f"admin:v2:profile:{number}")],
    ])


def _archive_with_reason(update: Any, context: Any, number: int, reason: str | None) -> int:
    if not _manager(update, context):
        return END
    with _session(context) as session:
        profile = ProfileRepository(session).get(number)
        if profile is None:
            return END
        profile.status = "inactive"
        meta = get_profile_meta(session, profile.id, True)
        meta.archive_status = "archived"
        meta.archive_reason = reason or None
        meta.archived_at = datetime.now(timezone.utc)
        meta.publication_status = "unpublished"
        log_admin_action(session, int(update.effective_user.id), "profile_archive", "profile", number, {"reason": reason})
        session.commit()
    context.user_data.clear()
    return END


async def _dashboard_home(update: Any, context: Any) -> int:
    with _session(context) as session:
        admin_v2.expire_reservations(session)
        snapshot = metrics(session)
    await update.callback_query.edit_message_text(_dashboard_text(snapshot), reply_markup=_dashboard_keyboard())
    return END


async def _show_section(update: Any, context: Any, section: str) -> int:
    data = {
        "ads": ("🔎 الإعلانات والبحث", "استخدم القسم للوصول للبحث الذكي، قوائم الإعلانات، الحالات والجودة.", _ads_section_keyboard()),
        "orders": ("💳 الطلبات والتواصل", "كل ما يخص طلبات التواصل والدفع والمتابعة من مكان واحد.", _orders_section_keyboard()),
        "reservations": ("🔒 الحجوزات", "العروض المحجوزة مع إمكان فك الحجز أو تمديده.", _section_keyboard("الحجوزات", [[InlineKeyboardButton("🔒 الحجوزات الحالية", callback_data="admin:v2:reservations:0")]])),
        "publishing": ("📣 النشر والمحتوى", "إدارة الجاهز للنشر والمنشور والمحتوى قبل النشر.", _section_keyboard("النشر والمحتوى", [
            [InlineKeyboardButton("🟢 جاهزة للنشر", callback_data="admin:v2:profiles:0:ready")],
            [InlineKeyboardButton("📤 المنشورة", callback_data="admin:v2:profiles:0:published")],
            [InlineKeyboardButton("⚠️ بحاجة استكمال", callback_data="admin:v2:profiles:0:incomplete")],
        ])),
        "reports": ("📊 التقارير والمتابعة", "ملخصات الأداء والإحصائيات وسجل المتابعة التشغيلي.", _section_keyboard("التقارير والمتابعة", [
            [InlineKeyboardButton("📊 التقارير", callback_data="admin:v2:reports")],
            [InlineKeyboardButton("🧾 سجل العمليات", callback_data="admin:v2:audit")],
        ])),
        "security": ("🛡️ الأمان والنسخ", "النسخ الاحتياطية والعمليات الحساسة وسجل العمليات.", _section_keyboard("الأمان والنسخ", [
            [InlineKeyboardButton("💾 النسخ الاحتياطية", callback_data="admin:v2:backups")],
            [InlineKeyboardButton("🧾 سجل العمليات", callback_data="admin:v2:audit")],
            [InlineKeyboardButton("⚠️ منطقة الخطر", callback_data="admin:v2:danger")],
        ])),
        "settings": ("⚙️ الإعدادات", "إعدادات الدفع والصلاحيات والذكاء الاصطناعي وحالة النظام.", _settings_section_keyboard()),
    }
    title, description, keyboard = data[section]
    await update.callback_query.edit_message_text(f"{title}\n\n{description}", reply_markup=keyboard)
    return END


async def _show_ads_gender(update: Any, context: Any) -> int:
    await update.callback_query.edit_message_text("👩 حسب الجنس\n\nاختار النوع:", reply_markup=_section_keyboard("الجنس", [
        [InlineKeyboardButton("👩 العرائس", callback_data="admin:v2:profiles:0:female")],
        [InlineKeyboardButton("🤵 العرسان", callback_data="admin:v2:profiles:0:male")],
    ]))
    return END


async def _show_ads_status(update: Any, context: Any) -> int:
    await update.callback_query.edit_message_text("📊 حسب الحالة\n\nاختار الحالة:", reply_markup=_section_keyboard("الحالة", [
        [InlineKeyboardButton("✅ المتاحة", callback_data="admin:v2:profiles:0:active"), InlineKeyboardButton("🔒 المحجوزة", callback_data="admin:v2:profiles:0:reserved")],
        [InlineKeyboardButton("⛔ المعطلة", callback_data="admin:v2:profiles:0:inactive"), InlineKeyboardButton("🗃️ الأرشيف", callback_data="admin:v2:profiles:0:archived")],
    ]))
    return END


async def _show_ads_quality(update: Any, context: Any) -> int:
    await update.callback_query.edit_message_text("⭐ الجودة والنشر\n\nاختار الفئة:", reply_markup=_section_keyboard("الجودة والنشر", [
        [InlineKeyboardButton("⚠️ بحاجة استكمال", callback_data="admin:v2:profiles:0:incomplete")],
        [InlineKeyboardButton("🟢 جاهزة للنشر", callback_data="admin:v2:profiles:0:ready"), InlineKeyboardButton("📤 المنشورة", callback_data="admin:v2:profiles:0:published")],
    ]))
    return END


async def _show_settings_subsection(update: Any, context: Any, subsection: str) -> int:
    settings = context.application.bot_data["settings"]
    if subsection == "payments":
        with _session(context) as session:
            amount = admin_v2.service_price(session)
            method = admin_v2.payment_method(session)
        await update.callback_query.edit_message_text(
            "💵 الدفع والأسعار\n\n"
            f"💵 سعر الخدمة: {amount:g} USD\n"
            f"💳 طريقة الدفع: {method}",
            reply_markup=_section_keyboard("الدفع والأسعار", [
                [InlineKeyboardButton("✏️ تغيير السعر", callback_data="admin:v2:settings:price")],
                [InlineKeyboardButton("✏️ تغيير طريقة الدفع", callback_data="admin:v2:settings:method")],
            ]),
        )
    elif subsection == "roles":
        access = getattr(settings, "admin_access", None)
        role_lines = []
        for uid in sorted(settings.admin_user_ids):
            role_lines.append(f"👤 {uid} — {access.role_for(uid) if access else 'owner'}")
        await update.callback_query.edit_message_text(
            "👑 الأدمن والصلاحيات\n\n" + ("\n".join(role_lines) if role_lines else "لا يوجد أدمنات مسجلون."),
            reply_markup=_section_keyboard("الأدمن والصلاحيات", [
                [InlineKeyboardButton("ℹ️ طريقة إدارة الصلاحيات", callback_data="admin:v2:settings:roles")],
            ]),
        )
    elif subsection == "ai":
        await update.callback_query.edit_message_text(
            "🤖 الذكاء الاصطناعي\n\n"
            f"الحالة: {'✅ مهيأ' if settings.ai_api_key else '❌ غير مهيأ'}\n"
            "مفتاح API لا يظهر داخل لوحة الأدمن.",
            reply_markup=_section_keyboard("الذكاء الاصطناعي", [
                [InlineKeyboardButton("🔧 فحص حالة النظام", callback_data="admin:v2:section:settings:status")],
            ]),
        )
    elif subsection == "status":
        with _session(context) as session:
            db_ok = True
            try:
                session.execute(text("SELECT 1"))
            except Exception:
                db_ok = False
        await update.callback_query.edit_message_text(
            "🔧 حالة النظام\n\n"
            f"🗄️ قاعدة البيانات: {'✅ سليمة' if db_ok else '❌ يوجد خلل'}\n"
            f"🤖 Gemini: {'✅ مهيأ' if settings.ai_api_key else '❌ غير مهيأ'}\n"
            f"🔐 حساب الأدمن: {'✅ مفعل' if settings.admin_user_ids else '❌ غير مهيأ'}",
            reply_markup=_section_keyboard("حالة النظام", [[InlineKeyboardButton("🔄 تحديث", callback_data="admin:v2:section:settings:status")]]),
        )
    return END


async def _show_reservations_plus(update: Any, context: Any, page: int) -> int:
    with _session(context) as session:
        admin_v2.expire_reservations(session)
        stmt = select(Profile, ProfileAdminMeta).join(ProfileAdminMeta, ProfileAdminMeta.profile_id == Profile.id).where(Profile.status == "reserved").order_by(desc(ProfileAdminMeta.reserved_at)).offset(page * 10).limit(11)
        rows = list(session.execute(stmt).all()); has_next = len(rows) > 10; rows = rows[:10]
    if not rows:
        await update.callback_query.edit_message_text("🔒 ما في عروض محجوزة حالياً.", reply_markup=_dashboard_keyboard())
        return END
    text_body = "🔒 الحجوزات\n\n"; buttons=[]
    for profile, meta in rows:
        expiry = meta.reservation_expires_at.strftime("%Y-%m-%d %H:%M") if meta.reservation_expires_at else "بدون انتهاء"
        text_body += f"📌 {profile.request_number} — {profile.name or 'بدون اسم'} — {profile.age} سنة — {profile.residence}\n⏰ {expiry}\n💬 {meta.reservation_reason or 'بدون سبب'}\n\n"
        buttons.append([
            InlineKeyboardButton(f"📌 عرض {profile.request_number}", callback_data=f"admin:v2:profile:{profile.request_number}"),
            InlineKeyboardButton("🔓 فك", callback_data=f"admin:v2:unreserve:{profile.request_number}"),
            InlineKeyboardButton("➕ تمديد", callback_data=f"admin:v2:reservation:extend:{profile.request_number}"),
        ])
    nav=[]
    if page > 0: nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin:v2:reservations:{page-1}"))
    if has_next: nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin:v2:reservations:{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    await update.callback_query.edit_message_text(text_body, reply_markup=InlineKeyboardMarkup(buttons)); return END


async def admin_callback(update: Any, context: Any) -> int:
    user = update.effective_user
    if user is None:
        return END
    context.user_data["v2_admin_user_id"] = int(user.id)
    data = update.callback_query.data or ""
    role = _role(context, int(user.id))

    if data == "admin:v2:dashboard":
        return await _dashboard_home(update, context)
    if data.startswith("admin:v2:section:"):
        parts = data.split(":")
        if parts[3] == "ads" and len(parts) == 5:
            if parts[4] == "gender": return await _show_ads_gender(update, context)
            if parts[4] == "status": return await _show_ads_status(update, context)
            if parts[4] == "quality": return await _show_ads_quality(update, context)
        if parts[3] == "settings" and len(parts) == 5:
            return await _show_settings_subsection(update, context, parts[4])
        if parts[3] in {"ads", "orders", "reservations", "publishing", "reports", "security", "settings"} and len(parts) == 4:
            return await _show_section(update, context, parts[3])

    if role == "viewer" and (
        data.startswith("admin:delete") or data.startswith("admin:disable") or data.startswith("admin:reserve") or
        data.startswith("admin:unreserve") or data.startswith("admin:edit") or data.startswith("admin:add") or
        data.startswith("admin:v2:delete") or data.startswith("admin:v2:archive") or data.startswith("admin:v2:reactivate") or
        data.startswith("admin:v2:reserve") or data.startswith("admin:v2:unreserve") or data.startswith("admin:v2:reservation:extend") or
        data.startswith("admin:v2:backup:create") or data.startswith("admin:v2:backup:restore") or
        data.startswith("admin:v2:settings:price") or data.startswith("admin:v2:settings:method") or data.startswith("admin:v2:danger")
    ):
        await update.callback_query.answer("👀 حساب المشاهدة لا يملك صلاحية التعديل أو الحذف.", show_alert=True)
        return END

    if data.startswith("admin:v2:archive:"):
        number = int(data.rsplit(":", 1)[1]) if data.count(":") == 3 else None
        if data.startswith("admin:v2:archive:reason:"):
            parts=data.split(":",4); number=int(parts[4]); reason=parts[5] if len(parts)>5 else None
            await update.callback_query.answer()
            _archive_with_reason(update, context, number, reason)
            await update.callback_query.edit_message_text(f"📦 تمت أرشفة الإعلان {number}.\n\n💬 السبب: {reason or 'بدون سبب'}\n🔒 البيانات بقيت محفوظة.", reply_markup=_dashboard_keyboard())
            return END
        if data.startswith("admin:v2:archive:custom:"):
            number=int(data.rsplit(":",1)[1]); context.user_data.update({"v2_flow":"archive_custom_reason","v2_archive_number":number})
            await update.callback_query.edit_message_text("✍️ اكتب سبب الأرشفة:", reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT
        number=int(data.rsplit(":",1)[1])
        if not _manager(update, context): await update.callback_query.answer("❌ للمديرين فقط.", show_alert=True); return END
        await update.callback_query.edit_message_text(f"📦 أرشفة الإعلان {number}\n\nاختار سبب الأرشفة:", reply_markup=_archive_keyboard(number)); return END

    if data.startswith("admin:v2:reservation:extend:"):
        number=int(data.rsplit(":",1)[1])
        await update.callback_query.edit_message_text("➕ كم يوم بدك تمدد الحجز؟", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("7 أيام", callback_data=f"admin:v2:reservation:extend:{number}:7"), InlineKeyboardButton("14 يوم", callback_data=f"admin:v2:reservation:extend:{number}:14")],
            [InlineKeyboardButton("30 يوم", callback_data=f"admin:v2:reservation:extend:{number}:30"), InlineKeyboardButton("بدون انتهاء", callback_data=f"admin:v2:reservation:extend:{number}:0")],
            [InlineKeyboardButton("⬅️ الحجوزات", callback_data="admin:v2:reservations:0")],
        ])); return END
    if re.match(r"^admin:v2:reservation:extend:\d+:\d+$", data):
        _,_,_,_,number_str,days_str=data.split(":"); number=int(number_str); days=int(days_str)
        with _session(context) as session:
            profile=ProfileRepository(session).get(number)
            if not profile: return END
            meta=get_profile_meta(session,profile.id,True)
            now=datetime.now(timezone.utc)
            base=meta.reservation_expires_at if meta.reservation_expires_at and meta.reservation_expires_at>now else now
            meta.reservation_expires_at=base+timedelta(days=days) if days else None
            log_admin_action(session,int(user.id),"reservation_extend","profile",number,{"days":days}); session.commit()
        await update.callback_query.edit_message_text(f"✅ تم تمديد حجز الإعلان {number}.", reply_markup=_dashboard_keyboard()); return END

    if data.startswith("admin:v2:reservations:"):
        try: page=int(data.rsplit(":",1)[1])
        except ValueError: page=0
        return await _show_reservations_plus(update,context,page)

    if data == "admin:v2:danger":
        await update.callback_query.edit_message_text("🛑 منطقة الخطر\n\nالحذف النهائي محمي بنسخة احتياطية وتأكيد كتابي.\n\nاختر العملية:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ حذف إعلان/إعلانات نهائياً", callback_data="admin:v2:danger:selected")],
            [InlineKeyboardButton("☢️ حذف كل الإعلانات نهائياً", callback_data="admin:v2:danger:all")],
            [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
        ])); return END
    if data == "admin:v2:danger:selected":
        context.user_data["v2_flow"]="danger_selected"; await update.callback_query.edit_message_text("✍️ اكتب أرقام الإعلانات مفصولة بفواصل. مثال: 101, 104, 108", reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT
    if data == "admin:v2:danger:all":
        if not _manager(update,context): await update.callback_query.answer("❌ للمديرين فقط.",show_alert=True); return END
        context.user_data["v2_flow"]="danger_all"; await update.callback_query.edit_message_text("☢️ حذف شامل نهائي\n\nسيتم إنشاء نسخة احتياطية تلقائياً قبل الحذف.\n\nاكتب **حذف كل البيانات نهائياً** للتأكيد.",parse_mode="Markdown",reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT

    if data == "admin:v2:audit:filter":
        context.user_data["v2_flow"]="audit_filter"; await update.callback_query.edit_message_text("🧾 فلترة السجل\n\nاكتب مثلاً:\nadmin=123\naction=profile_add\nأو اكتب أحدهما فقط.",reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT

    if data == "admin:v2:settings":
        with _session(context) as session:
            db_ok=True
            try: session.execute(text("SELECT 1"))
            except Exception: db_ok=False
            m=metrics(session)
        settings=context.application.bot_data["settings"]; access=getattr(settings,"admin_access",None)
        roles="\n".join(f"{uid}: {access.role_for(uid)}" for uid in sorted(settings.admin_user_ids)) if access else "غير مفصلة"
        await update.callback_query.edit_message_text(
            "⚙️ إعدادات الأدمن\n\n"
            f"💵 سعر الخدمة: قيد الإعداد من داخل النظام\n"
            f"💳 طريقة الدفع: قيد الإعداد من داخل النظام\n"
            f"🤖 Gemini: {'✅ مهيأ' if settings.ai_api_key else '❌ غير مهيأ'}\n"
            f"🗄️ قاعدة البيانات: {'✅ سليمة' if db_ok else '❌ يوجد خلل'}\n\n"
            "👑 الصلاحيات:\n"+roles,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💵 تغيير السعر", callback_data="admin:v2:settings:price"),InlineKeyboardButton("💳 تغيير طريقة الدفع",callback_data="admin:v2:settings:method")],
                [InlineKeyboardButton("👑 الصلاحيات",callback_data="admin:v2:settings:roles")],[InlineKeyboardButton("⬅️ لوحة الأدمن",callback_data="admin:v2:dashboard")]
            ])); return END

    return await admin_v2.admin_callback(update,context)


async def admin_text(update: Any, context: Any) -> int:
    flow=context.user_data.get("v2_flow"); text_value=(update.effective_message.text or "").strip()
    if flow == "archive_custom_reason":
        number=int(context.user_data["v2_archive_number"]); _archive_with_reason(update,context,number,text_value); await update.effective_message.reply_text(f"📦 تمت أرشفة الإعلان {number}.\n💬 السبب: {text_value}",reply_markup=_dashboard_keyboard()); context.user_data.clear(); return END
    if flow == "danger_selected":
        numbers=sorted({int(x) for x in re.split(r"[\s,،;]+",text_value) if x.strip().isdigit()})
        if not numbers: await update.effective_message.reply_text("❌ ما وصلني أرقام صالحة.",reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT
        context.user_data.update({"v2_flow":"danger_selected_confirm","v2_delete_numbers":numbers})
        await update.effective_message.reply_text("⚠️ سيتم حذف الإعلانات: " + ", ".join(map(str,numbers)) + " نهائياً بعد نسخة احتياطية.\n\nاكتب **حذف المحدد نهائياً** للتأكيد.",parse_mode="Markdown",reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT
    if flow == "danger_selected_confirm":
        if text_value != "حذف المحدد نهائياً": await update.effective_message.reply_text("❌ لم يتم الحذف.",reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT
        numbers=context.user_data["v2_delete_numbers"]
        with _session(context) as session:
            create_backup(session,int(update.effective_user.id),"قبل حذف إعلانات محددة من منطقة الخطر")
            count=ProfileRepository(session).delete_requests(numbers); log_admin_action(session,int(update.effective_user.id),"bulk_profile_delete","profile",None,{"count":count,"numbers":numbers}); session.commit()
        context.user_data.clear(); await update.effective_message.reply_text(f"✅ تم حذف {len(numbers)} إعلان نهائياً بعد إنشاء نسخة احتياطية.",reply_markup=_dashboard_keyboard()); return END
    if flow == "danger_all":
        if text_value != "حذف كل البيانات نهائياً": await update.effective_message.reply_text("❌ لم يتم الحذف.",reply_markup=admin_v2._back_keyboard()); return ADMIN_V2_INPUT
        if not _manager(update,context): await update.effective_message.reply_text("❌ للمديرين فقط."); return END
        with _session(context) as session:
            create_backup(session,int(update.effective_user.id),"قبل حذف كل الإعلانات من منطقة الخطر")
            count=ProfileRepository(session).delete_all(); log_admin_action(session,int(update.effective_user.id),"bulk_profile_delete_all","profile",None,{"count":count}); session.commit()
        context.user_data.clear(); await update.effective_message.reply_text(f"✅ تم حذف {count} إعلان نهائياً بعد إنشاء نسخة احتياطية.",reply_markup=_dashboard_keyboard()); return END
    if flow == "audit_filter":
        admin_id=None; action=None
        m=re.search(r"admin\s*=\s*(\d+)",text_value,re.I)
        if m: admin_id=int(m.group(1))
        m=re.search(r"action\s*=\s*([A-Za-z0-9_:-]+)",text_value,re.I)
        if m: action=m.group(1)
        with _session(context) as session: rows=list_audit_logs(session,25,admin_id,action)
        body="🧾 سجل العمليات المفلتر\n\n"+("لا توجد نتائج." if not rows else "\n".join(f"{r.created_at.strftime('%m-%d %H:%M')} — {r.admin_user_id} — {r.action} — {r.entity_number or ''}" for r in rows))
        context.user_data.clear(); await update.effective_message.reply_text(body,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ لوحة الأدمن",callback_data="admin:v2:dashboard")]])); return END
    return await admin_v2.admin_text(update,context)


async def admin_photo(update: Any, context: Any) -> int:
    return await admin_v2.admin_photo(update,context)