"""Client-facing browsing, natural-language search, and manual payment flow."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.database.repositories import OrderRepository, ProfileFilters, ProfileRepository
from app.keyboards.client import client_main_keyboard, client_profile_keyboard, client_results_keyboard, client_search_keyboard
from app.services.profiles import format_client_profile, mask_phone
from app.services.search import filters_from_ai, merge_filters, parse_search_text

END = -1
SEARCH_TEXT = 30
PAYMENT_TX = 31


def next_search_state(has_valid_filters: bool) -> int:
    return END if has_valid_filters else SEARCH_TEXT


def _settings(context: Any):
    return context.application.bot_data["settings"]


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _has_filters(filters: ProfileFilters) -> bool:
    return any((filters.gender, filters.residence, filters.age_min, filters.age_max, filters.marital_status, filters.occupation, filters.education, filters.children_min is not None, filters.children_max is not None))


def _search_prompt(target_gender: str | None = None) -> str:
    if target_gender == "male":
        return "🤵 دورولي على عريس مناسب\n\nاكتب المواصفات بطريقتك، وأنا بفهم المعنى وبحوّله لفلاتر بحث فعلية.\nمثلاً: بدي عريس من دمشق عمره بين 28 و35 وما بدخن.\n\n⬅️ فيك ترجع للقائمة الرئيسية من الزر تحت."
    if target_gender == "female":
        return "👰 دورولي على عروس مناسبة\n\nاكتب المواصفات بطريقتك، وأنا بفهم المعنى وبحوّله لفلاتر بحث فعلية.\nمثلاً: بدي بنت من الشام عمرها بين 22 و28 ومطلقة بدون ولاد.\n\n⬅️ فيك ترجع للقائمة الرئيسية من الزر تحت."
    return "🔎 اكتب طلب البحث بطريقتك.\n\nما في داعي تلتزم بصيغة محددة؛ اكتب متل ما بتحكي، وأنا بفهم الطلب وبحوّله لفلاتر قاعدة بيانات.\nمثلاً: بدي بنت من حمص عمرها حوالي 25، أو بدي عريس ساكن بريف حماة.\n\n⬅️ فيك ترجع للقائمة الرئيسية من الزر تحت."


async def client_callback(update: Any, context: Any) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "client:search":
        context.user_data.clear()
        context.user_data["client_flow"] = "search"
        await query.edit_message_text(_search_prompt(), reply_markup=client_search_keyboard())
        return SEARCH_TEXT
    if data.startswith("client:match:"):
        target_gender = data.rsplit(":", 1)[1]
        if target_gender not in {"male", "female"}:
            return END
        context.user_data.clear()
        context.user_data["client_flow"] = "search"
        context.user_data["search_target_gender"] = target_gender
        await query.edit_message_text(_search_prompt(target_gender), reply_markup=client_search_keyboard())
        return SEARCH_TEXT
    if data == "client:list":
        context.user_data.clear()
        await _show_latest(update, context)
        return END
    if data == "client:about":
        context.user_data.clear()
        await query.edit_message_text("ℹ️ طريقة العمل\n\nبتقدر تتصفح عروض الزواج وتبحث بالكلام العادي عن العمر ومكان السكن والحالة الاجتماعية والعمل والتعليم وعدد الأولاد.\n\n🧠 الذكاء الاصطناعي بيفهم طلبك وبيحوّله لفلاتر، وبعدها قاعدة البيانات هي اللي بتطلع النتائج.\n\n🔒 معلومات التواصل الخاصة ما بتظهر بشكل مكشوف للمستخدمين.", reply_markup=client_main_keyboard())
        return END
    if data == "client:menu":
        context.user_data.clear()
        await query.edit_message_text("🌸 القائمة الرئيسية", reply_markup=client_main_keyboard())
        return END
    if data.startswith("client:profile:"):
        return await _show_profile(update, context, _number_suffix(data))
    if data.startswith("client:request:"):
        return await _create_contact_order(update, context, _number_suffix(data))
    return END


async def client_text(update: Any, context: Any) -> int:
    text = (update.effective_message.text or "").strip()
    if context.user_data.get("client_flow") == "search":
        return await _run_search(update, context, text)
    if context.user_data.get("client_flow") == "payment":
        return await _save_transaction(update, context, text)
    await update.effective_message.reply_text("🌸 استخدم الأزرار الموجودة بالقائمة.", reply_markup=client_main_keyboard())
    return END


async def _run_search(update: Any, context: Any, text: str) -> int:
    base = parse_search_text(text)
    target_gender = context.user_data.get("search_target_gender")
    if target_gender in {"male", "female"}:
        base = ProfileFilters(gender=target_gender, residence=base.residence, age_min=base.age_min, age_max=base.age_max, marital_status=base.marital_status, occupation=base.occupation, education=base.education, children_min=base.children_min, children_max=base.children_max, limit=base.limit)
    filters = base
    ai = context.application.bot_data["ai_service"]
    ai_error = False
    if ai.is_configured:
        try:
            ai_filters = filters_from_ai(await ai.parse_search_filters(text), text)
            if target_gender in {"male", "female"}:
                ai_filters = ProfileFilters(gender=target_gender, residence=ai_filters.residence, age_min=ai_filters.age_min, age_max=ai_filters.age_max, marital_status=ai_filters.marital_status, occupation=ai_filters.occupation, education=ai_filters.education, children_min=ai_filters.children_min, children_max=ai_filters.children_max, limit=ai_filters.limit)
            filters = merge_filters(base, ai_filters)
        except Exception:
            ai_error = True
    if not _has_filters(filters):
        message = "⚠️ ما قدرت أفهم طلب البحث بشكل كافي. جرّب تكتب مثلاً: بدي بنت من دمشق بين 22 و28 سنة عزباء."
        if ai_error:
            message += "\n\n⚠️ الذكاء الاصطناعي ما قدر يحلل الطلب حالياً."
        await update.effective_message.reply_text(message, reply_markup=client_search_keyboard())
        return SEARCH_TEXT
    with _session(context) as session:
        rows = ProfileRepository(session).search(filters)
    context.user_data.clear()
    if not rows:
        await update.effective_message.reply_text("🔎 ما لقينا عروض مطابقة لهالمواصفات. جرّب تخفف شرط أو توسّع مكان السكن/العمر.", reply_markup=client_main_keyboard())
        return END
    await update.effective_message.reply_text(f"💗 لقينا {len(rows)} عرض مناسب مبدئياً.\n\n" + "\n".join(f"📌 طلب {row.request_number} — {row.age} سنة — {row.residence} — {('🔒 محجوز' if row.status == 'reserved' else '✅ متاح')}" for row in rows), reply_markup=client_results_keyboard([row.request_number for row in rows]))
    return END


async def _show_latest(update: Any, context: Any) -> None:
    with _session(context) as session:
        rows = ProfileRepository(session).latest(10)
    if not rows:
        await update.callback_query.edit_message_text("📋 ما في عروض متاحة حالياً.", reply_markup=client_main_keyboard())
        return
    await update.callback_query.edit_message_text("📋 أحدث العروض:\n\n" + "\n".join(f"📌 طلب {row.request_number} — {row.age} سنة — {row.residence} — {('🔒 محجوز' if row.status == 'reserved' else '✅ متاح')}" for row in rows), reply_markup=client_results_keyboard([row.request_number for row in rows]))


async def _show_profile(update: Any, context: Any, request_number: int | None) -> int:
    if request_number is None:
        return END
    with _session(context) as session:
        repo = ProfileRepository(session)
        public = repo.get_public(request_number)
        contact = repo.get_contact(request_number)
    if public is None or public.get("status") == "inactive":
        await update.callback_query.edit_message_text("❌ ما عاد هالعرض متاح.", reply_markup=client_main_keyboard())
        return END
    masked = mask_phone(contact.phone) if contact and contact.phone else None
    await update.callback_query.edit_message_text(format_client_profile(public, masked_phone=masked), reply_markup=client_profile_keyboard(request_number, public.get("status", "active")))
    return END


async def _create_contact_order(update: Any, context: Any, request_number: int | None) -> int:
    if request_number is None:
        return END
    user = update.effective_user
    with _session(context) as session:
        profile = ProfileRepository(session).get(request_number)
        if profile is None or profile.status == "inactive":
            await update.callback_query.edit_message_text("❌ ما عاد هالعرض متاح.", reply_markup=client_main_keyboard())
            return END
        if profile.status == "reserved":
            await update.callback_query.edit_message_text("🔒 هالعرض محجوز حالياً، لذلك ما فينا نفتح طلب تواصل عليه.", reply_markup=client_main_keyboard())
            return END
        order = OrderRepository(session).create_contact_request(user.id, request_number, Decimal("5.00"), "شام كاش")
        if order is None:
            await update.callback_query.edit_message_text("❌ ما قدرنا ننشئ طلب التواصل.", reply_markup=client_main_keyboard())
            return END
        session.commit()
        number = order.order_number
    context.user_data.clear()
    context.user_data["client_flow"] = "payment"
    context.user_data["pending_order_number"] = number
    await update.callback_query.edit_message_text(f"📩 تسجّل طلب التواصل رقم {number}.\n\n💵 قيمة الخدمة: 5 دولار\n💳 الدفع: شام كاش\n\nرح تتواصل معك الخطابة على حسابك هون وتشرحلك طريقة الدفع. بعد تأكيد الدفع، بتتم متابعة طلب التواصل معك.\n\n⬅️ فيك ترجع للقائمة الرئيسية من الزر تحت.", reply_markup=client_search_keyboard())
    await _notify_admins(context, number, user, request_number)
    return PAYMENT_TX


async def _save_transaction(update: Any, context: Any, text: str) -> int:
    order_number = context.user_data.get("pending_order_number")
    if not order_number:
        await update.effective_message.reply_text("❌ ما لقينا طلب الدفع.", reply_markup=client_main_keyboard())
        return END
    with _session(context) as session:
        repo = OrderRepository(session)
        order = repo.get(order_number)
        if order is None or order.user_telegram_id != update.effective_user.id:
            await update.effective_message.reply_text("❌ ما لقينا طلب الدفع.", reply_markup=client_main_keyboard())
            return END
        repo.set_transaction_id(order_number, text)
        session.commit()
    context.user_data.clear()
    await update.effective_message.reply_text(f"✅ تم تسجيل رقم العملية للطلب {order_number}. رح تراجعه الصفحة يدوياً.", reply_markup=client_main_keyboard())
    return END


async def _notify_admins(context: Any, order_number: int, user: Any, profile_request: int) -> None:
    username = f"@{user.username}" if getattr(user, "username", None) else "بدون Username"
    display_name = " ".join(part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part) or "بدون اسم"
    for admin_id in _settings(context).admin_user_ids:
        try:
            await context.application.bot.send_message(admin_id, "💳 طلب تواصل جديد\n\n" f"📌 طلب الدفع: {order_number}\n" f"📌 الإعلان المطلوب: {profile_request}\n" "💵 القيمة: 5 USD\n\n" f"👤 اسم حساب العميل: {display_name}\n" f"🔹 Username: {username}\n" f"🆔 Telegram User ID: {user.id}\n\n" "📞 تواصلوا معه لشرح طريقة الدفع ومتابعة الطلب.")
        except Exception:
            pass


def _number_suffix(data: str | None) -> int | None:
    if not data:
        return None
    try:
        return int(data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None
