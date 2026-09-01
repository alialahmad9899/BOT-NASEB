"""Client contact-request flow: collect and confirm WhatsApp, then let the matchmaker handle payment."""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.database.repositories import OrderRepository, ProfileRepository
from app.services.admin_meta import get_order_meta, payment_method, service_price
from app.services.payment import normalize_whatsapp

WHATSAPP_INPUT = 40
WHATSAPP_CONFIRM = 41
END = ConversationHandler.END


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _payment_pending_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 طلباتي", callback_data="client:orders")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])


def _input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء", callback_data="client:whatsapp:cancel")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="client:menu")],
    ])


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data="client:whatsapp:confirm")],
        [InlineKeyboardButton("✏️ تعديل الرقم", callback_data="client:whatsapp:edit")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="client:whatsapp:cancel")],
    ])


def _request_number(data: str | None) -> int | None:
    if not data:
        return None
    try:
        return int(data.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None


async def request_contact_callback(update: Any, context: Any) -> int:
    query = update.callback_query
    await query.answer()
    request_number = _request_number(query.data)
    if request_number is None:
        await query.edit_message_text("❌ ما فهمت رقم الإعلان.", reply_markup=_payment_pending_keyboard())
        return END
    with _session(context) as session:
        profile = ProfileRepository(session).get(request_number)
        amount = service_price(session)
        method = payment_method(session)
    if profile is None or profile.status == "inactive":
        await query.edit_message_text("❌ هالإعلان ما عاد متاح.", reply_markup=_payment_pending_keyboard())
        return END
    if profile.status == "reserved":
        await query.edit_message_text("🔒 هالإعلان محجوز حالياً، فما فينا نفتح طلب تواصل عليه.", reply_markup=_payment_pending_keyboard())
        return END
    context.user_data.clear()
    context.user_data["payment_profile_request"] = request_number
    context.user_data["payment_amount"] = str(amount)
    context.user_data["payment_method"] = method
    await query.edit_message_text(
        "📩 طلب التواصل\n\n"
        f"قيمة الخدمة {amount:g} دولار.\n\n"
        "حتى تتواصل معك الخطّابة بخصوص الدفع،\n"
        "ابعت رقم الواتساب اللي بدك نحكيك عليه.\n\n"
        "📱 اكتب رقم واتساب:",
        reply_markup=_input_keyboard(),
    )
    return WHATSAPP_INPUT


async def payment_whatsapp_text(update: Any, context: Any) -> int:
    normalized = normalize_whatsapp((update.effective_message.text or "").strip())
    if normalized is None:
        await update.effective_message.reply_text(
            "❌ الرقم مو بصيغة سورية صحيحة.\n\nمثال: 09xxxxxxxx أو +9639xxxxxxxx.",
            reply_markup=_input_keyboard(),
        )
        return WHATSAPP_INPUT

    request_number = context.user_data.get("payment_profile_request")
    if not request_number:
        context.user_data.clear()
        await update.effective_message.reply_text(
            "❌ انتهت جلسة طلب التواصل. افتح الإعلان وجرّب من جديد.",
            reply_markup=_payment_pending_keyboard(),
        )
        return END

    context.user_data["pending_whatsapp"] = normalized
    await update.effective_message.reply_text(
        "✅ تأكيد رقم الواتساب\n\n"
        f"📱 {normalized}\n\n"
        "هل الرقم صحيح؟",
        reply_markup=_confirm_keyboard(),
    )
    return WHATSAPP_CONFIRM


async def payment_whatsapp_confirm(update: Any, context: Any) -> int:
    query = update.callback_query
    await query.answer()
    request_number = context.user_data.get("payment_profile_request")
    whatsapp = context.user_data.get("pending_whatsapp")
    if not request_number or not whatsapp:
        context.user_data.clear()
        await query.edit_message_text(
            "❌ انتهت جلسة طلب التواصل. افتح الإعلان وجرّب من جديد.",
            reply_markup=_payment_pending_keyboard(),
        )
        return END

    user = update.effective_user
    with _session(context) as session:
        amount = service_price(session)
        method = payment_method(session)
        order = OrderRepository(session).create_contact_request(
            user.id,
            int(request_number),
            amount,
            method,
        )
        if order is None:
            await query.edit_message_text(
                "❌ ما قدرنا نسجل طلب التواصل. تأكد أن الإعلان ما زال متاحاً.",
                reply_markup=_payment_pending_keyboard(),
            )
            return END
        order.whatsapp = whatsapp
        meta = get_order_meta(session, int(order.id), create=True)
        if meta:
            meta.payment_status = "pending"
            meta.contact_status = "new"
        session.commit()
        order_number = int(order.order_number)

    context.user_data.clear()
    await query.edit_message_text(
        "✅ تم تسجيل طلبك\n\n"
        f"📌 رقم الطلب: {order_number}\n\n"
        "📞 الخطّابة رح تتواصل معك على الواتساب\n"
        f"وتشرحلك طريقة الدفع عبر {method}.\n\n"
        "💛 شكراً لثقتك بصفحة لقاء ونصيب.",
        reply_markup=_payment_pending_keyboard(),
    )
    await _notify_admins(context, order_number, int(request_number), user, whatsapp, amount, method)
    return END


async def payment_whatsapp_edit(update: Any, context: Any) -> int:
    query = update.callback_query
    await query.answer()
    if "payment_profile_request" not in context.user_data:
        context.user_data.clear()
        await query.edit_message_text(
            "❌ انتهت جلسة طلب التواصل. افتح الإعلان وجرّب من جديد.",
            reply_markup=_payment_pending_keyboard(),
        )
        return END
    context.user_data.pop("pending_whatsapp", None)
    await query.edit_message_text(
        "✏️ تمام، اكتب رقم الواتساب من جديد:",
        reply_markup=_input_keyboard(),
    )
    return WHATSAPP_INPUT


async def payment_whatsapp_cancel(update: Any, context: Any) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("✅ تم إلغاء طلب التواصل.", reply_markup=_payment_pending_keyboard())
    return END


async def stale_payment_callback(update: Any, context: Any) -> int:
    """Handle old transaction buttons still present in messages sent before this release."""
    query = update.callback_query
    await query.answer("تم تغيير طريقة الدفع. ما عاد نطلب رقم العملية.", show_alert=True)
    await query.edit_message_text(
        "ℹ️ طريقة الدفع تغيرت. ما عاد في حاجة لإرسال رقم عملية.\n\n"
        "📱 إذا بدك تتابع طلب التواصل، افتح الإعلان من جديد وسجّل رقم الواتساب.",
        reply_markup=_payment_pending_keyboard(),
    )
    context.user_data.clear()
    return END


async def _notify_admins(context: Any, order_number: int, profile_request: int, user: Any, whatsapp: str, amount, method: str) -> None:
    username = f"@{user.username}" if getattr(user, "username", None) else "بدون Username"
    display_name = " ".join(
        part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part
    ) or "بدون اسم"
    for admin_id in context.application.bot_data["settings"].admin_user_ids:
        try:
            await context.application.bot.send_message(
                admin_id,
                "💗 طلب تواصل جديد\n\n"
                f"📌 رقم الطلب: {order_number}\n"
                f"📌 الإعلان المطلوب: {profile_request}\n"
                f"💵 قيمة الخدمة: {amount:g} دولار\n"
                f"💳 طريقة الدفع: {method}\n\n"
                f"👤 العميل: {display_name}\n"
                f"🔹 Username: {username}\n"
                f"🆔 Telegram ID: {user.id}\n"
                f"📱 WhatsApp: {whatsapp}\n\n"
                f"📞 الخطّابة تتواصل معه على الواتساب وتشرحله طريقة الدفع عبر {method}.\n"
                "⚠️ لا يوجد إدخال لرقم عملية؛ متابعة الدفع تتم يدوياً.",
            )
        except Exception:
            pass
