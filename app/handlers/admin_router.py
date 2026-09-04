"""Admin navigation shell.

Keeps the existing safety/feature router intact in ``admin_router_legacy`` while
presenting a compact, grouped dashboard with nested sections.
"""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.handlers import admin_router_legacy as _legacy

END = ConversationHandler.END
ADMIN_V2_INPUT = _legacy.ADMIN_V2_INPUT
admin_v2 = _legacy.admin_v2

# Backward-compatible exports for existing imports/tests.
_session = _legacy._session
_role = _legacy._role
_manager = _legacy._manager
_owner = _legacy._owner
_archive_keyboard = _legacy._archive_keyboard
_archive_with_reason = _legacy._archive_with_reason
_show_reservations_plus = _legacy._show_reservations_plus


def _home_keyboard() -> InlineKeyboardMarkup:
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


def _back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")]])


def _section(title: str, buttons: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    buttons = list(buttons)
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    return InlineKeyboardMarkup(buttons)


def _status_text(snapshot: dict[str, Any]) -> str:
    p = snapshot["profiles"]
    o = snapshot["orders"]
    return (
        "🔐 لوحة تحكم لقاء ونصيب\n\n"
        "📊 الحالة الآن\n"
        f"✅ متاحة: {p['active']}   🔒 محجوزة: {p['reserved']}   ⛔ معطلة: {p['inactive']}\n"
        f"🗃️ مؤرشفة: {p['archived']}\n"
        f"💳 متابعة: {o['pending']}   💰 مدفوعة: {o['paid']}   ✅ مكتملة: {o['completed']}\n\n"
        "اختار القسم اللي بدك تديره:"
    )


async def _dashboard(update: Any, context: Any) -> int:
    with _legacy._session(context) as session:
        _legacy.admin_v2.expire_reservations(session)
        snapshot = _legacy.metrics(session)
    await update.callback_query.edit_message_text(_status_text(snapshot), reply_markup=_home_keyboard())
    return END


async def _section_screen(update: Any, context: Any, name: str) -> int:
    screens: dict[str, tuple[str, InlineKeyboardMarkup]] = {
        "ads": (
            "🔎 الإعلانات والبحث\n\nمن هون بتوصل للبحث الذكي وقوائم الإعلانات والحالات.",
            _section("الإعلانات والبحث", [
                [InlineKeyboardButton("🔎 البحث الذكي", callback_data="admin:v2:search")],
                [InlineKeyboardButton("📋 كل الإعلانات", callback_data="admin:v2:profiles:0:all")],
                [InlineKeyboardButton("👩 حسب الجنس", callback_data="admin:v2:section:ads:gender"), InlineKeyboardButton("📊 حسب الحالة", callback_data="admin:v2:section:ads:status")],
                [InlineKeyboardButton("⭐ الجودة والنشر", callback_data="admin:v2:section:ads:quality")],
            ]),
        ),
        "orders": (
            "💳 الطلبات والتواصل\n\nإدارة طلبات التواصل والدفع والمتابعة.",
            _section("الطلبات والتواصل", [
                [InlineKeyboardButton("🆕 الجديدة", callback_data="admin:v2:orders:0:pending")],
                [InlineKeyboardButton("💰 المدفوعة", callback_data="admin:v2:orders:0:paid"), InlineKeyboardButton("✅ المكتملة", callback_data="admin:v2:orders:0:completed")],
                [InlineKeyboardButton("📋 كل الطلبات", callback_data="admin:v2:orders:0:all")],
            ]),
        ),
        "reservations": (
            "🔒 الحجوزات\n\nالعروض المحجوزة مع فك الحجز وتمديد المدة.",
            _section("الحجوزات", [[InlineKeyboardButton("🔒 الحجوزات الحالية", callback_data="admin:v2:reservations:0")]]),
        ),
        "publishing": (
            "📣 النشر والمحتوى\n\nجهّز الإعلانات للنشر وتابع حالتها.",
            _section("النشر والمحتوى", [
                [InlineKeyboardButton("🟢 جاهزة للنشر", callback_data="admin:v2:profiles:0:ready")],
                [InlineKeyboardButton("📤 المنشورة", callback_data="admin:v2:profiles:0:published")],
                [InlineKeyboardButton("⚠️ بحاجة استكمال", callback_data="admin:v2:profiles:0:incomplete")],
            ]),
        ),
        "reports": (
            "📊 التقارير والمتابعة\n\nإحصائيات الأداء وسجل المتابعة.",
            _section("التقارير والمتابعة", [
                [InlineKeyboardButton("📊 التقارير", callback_data="admin:v2:reports")],
                [InlineKeyboardButton("🧾 سجل العمليات", callback_data="admin:v2:audit")],
            ]),
        ),
        "security": (
            "🛡️ الأمان والنسخ\n\nالنسخ الاحتياطية والعمليات الحساسة.",
            _section("الأمان والنسخ", [
                [InlineKeyboardButton("💾 النسخ الاحتياطية", callback_data="admin:v2:backups")],
                [InlineKeyboardButton("🧾 سجل العمليات", callback_data="admin:v2:audit")],
                [InlineKeyboardButton("⚠️ منطقة الخطر", callback_data="admin:v2:danger")],
            ]),
        ),
        "settings": (
            "⚙️ الإعدادات\n\nكل إعداد بمجموعة مستقلة حتى تبقى الشاشة الرئيسية مرتبة.",
            _section("الإعدادات", [
                [InlineKeyboardButton("💵 الدفع والأسعار", callback_data="admin:v2:section:settings:payments")],
                [InlineKeyboardButton("👑 الأدمن والصلاحيات", callback_data="admin:v2:section:settings:roles")],
                [InlineKeyboardButton("🤖 الذكاء الاصطناعي", callback_data="admin:v2:section:settings:ai")],
                [InlineKeyboardButton("🔧 حالة النظام", callback_data="admin:v2:section:settings:status")],
            ]),
        ),
    }
    text, keyboard = screens[name]
    await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    return END


async def _ads_subsection(update: Any, context: Any, name: str) -> int:
    if name == "gender":
        keyboard = _section("حسب الجنس", [[InlineKeyboardButton("👩 العرائس", callback_data="admin:v2:profiles:0:female")], [InlineKeyboardButton("🤵 العرسان", callback_data="admin:v2:profiles:0:male")]])
        text = "👩 حسب الجنس\n\nاختار النوع:"
    elif name == "status":
        keyboard = _section("حسب الحالة", [[InlineKeyboardButton("✅ المتاحة", callback_data="admin:v2:profiles:0:active"), InlineKeyboardButton("🔒 المحجوزة", callback_data="admin:v2:profiles:0:reserved")], [InlineKeyboardButton("⛔ المعطلة", callback_data="admin:v2:profiles:0:inactive"), InlineKeyboardButton("🗃️ الأرشيف", callback_data="admin:v2:profiles:0:archived")]])
        text = "📊 حسب الحالة\n\nاختار الحالة:"
    else:
        keyboard = _section("الجودة والنشر", [[InlineKeyboardButton("⚠️ بحاجة استكمال", callback_data="admin:v2:profiles:0:incomplete")], [InlineKeyboardButton("🟢 جاهزة للنشر", callback_data="admin:v2:profiles:0:ready"), InlineKeyboardButton("📤 المنشورة", callback_data="admin:v2:profiles:0:published")]])
        text = "⭐ الجودة والنشر\n\nاختار الفئة:"
    await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    return END


async def _settings_subsection(update: Any, context: Any, name: str) -> int:
    settings = context.application.bot_data["settings"]
    if name == "payments":
        with _legacy._session(context) as session:
            amount = _legacy.admin_v2.service_price(session)
            method = _legacy.admin_v2.payment_method(session)
        text = f"💵 الدفع والأسعار\n\n💵 سعر الخدمة: {amount:g} USD\n💳 طريقة الدفع: {method}"
        keyboard = _section("الدفع والأسعار", [[InlineKeyboardButton("✏️ تغيير السعر", callback_data="admin:v2:settings:price")], [InlineKeyboardButton("✏️ تغيير طريقة الدفع", callback_data="admin:v2:settings:method")]])
    elif name == "roles":
        access = getattr(settings, "admin_access", None)
        lines = [f"👤 {uid} — {access.role_for(uid) if access else 'owner'}" for uid in sorted(settings.admin_user_ids)]
        text = "👑 الأدمن والصلاحيات\n\n" + ("\n".join(lines) if lines else "لا يوجد أدمنات.")
        keyboard = _section("الأدمن والصلاحيات", [[InlineKeyboardButton("ℹ️ تفاصيل إدارة الصلاحيات", callback_data="admin:v2:settings:roles")]])
    elif name == "ai":
        text = "🤖 الذكاء الاصطناعي\n\n" + ("✅ Gemini مهيأ" if settings.ai_api_key else "❌ Gemini غير مهيأ") + "\n\n🔒 مفتاح API لا يظهر داخل الواجهة."
        keyboard = _section("الذكاء الاصطناعي", [[InlineKeyboardButton("🔧 فحص حالة النظام", callback_data="admin:v2:section:settings:status")]])
    else:
        with _legacy._session(context) as session:
            db_ok = True
            try:
                session.execute(text("SELECT 1"))
            except Exception:
                db_ok = False
        text = "🔧 حالة النظام\n\n" + f"🗄️ قاعدة البيانات: {'✅ سليمة' if db_ok else '❌ يوجد خلل'}\n" + f"🤖 Gemini: {'✅ مهيأ' if settings.ai_api_key else '❌ غير مهيأ'}\n" + "🔐 الأدمن: ✅"
        keyboard = _section("حالة النظام", [[InlineKeyboardButton("🔄 تحديث", callback_data="admin:v2:section:settings:status")]])
    await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    return END


async def admin_callback(update: Any, context: Any) -> int:
    data = update.callback_query.data or ""
    if data == "admin:v2:add:save":
        return await admin_v2._save_add(update, context)
    if data.startswith("admin:v2:section:"):
        parts = data.split(":")
        if len(parts) == 4 and parts[3] in {"ads", "orders", "reservations", "publishing", "reports", "security", "settings"}:
            return await _section_screen(update, context, parts[3])
        if len(parts) == 5 and parts[3] == "ads" and parts[4] in {"gender", "status", "quality"}:
            return await _ads_subsection(update, context, parts[4])
        if len(parts) == 5 and parts[3] == "settings" and parts[4] in {"payments", "roles", "ai", "status"}:
            return await _settings_subsection(update, context, parts[4])
    if data == "admin:v2:dashboard" or data == "admin:menu":
        return await _dashboard(update, context)
    return await _legacy.admin_callback(update, context)


async def admin_text(update: Any, context: Any) -> int:
    return await _legacy.admin_text(update, context)


async def admin_photo(update: Any, context: Any) -> int:
    return await _legacy.admin_photo(update, context)