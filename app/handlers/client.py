"""Client-facing search, browsing, and manual payment flow."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.database.repositories import OrderRepository, ProfileRepository
from app.keyboards.client import client_main_keyboard, client_profile_keyboard, client_results_keyboard
from app.services.search import filters_from_ai, merge_filters, parse_search_text

END = -1
SEARCH_TEXT = 30
PAYMENT_TX = 31


def _settings(context: Any):
    return context.application.bot_data["settings"]


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


async def client_callback(update: Any, context: Any) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data in {"client:search", "client:match"}:
        context.user_data["client_flow"] = "search"
        await query.edit_message_text(
            "✍️ اكتب مواصفات البحث برسالة وحدة.\nمثال: بدي بنت من دمشق بين 22 و27، عزباء"
        )
        return SEARCH_TEXT
    if data == "client:list":
        await _show_latest(update, context)
        return END
    if data == "client:about":
        await query.edit_message_text(
            "ℹ️ طريقة العمل\n\nبتقدر تتصفح عروض الزواج وتبحث حسب المحافظة والمدينة والعمر والحالة والمهنة.\n\n🔒 معلومات التواصل الخاصة ما بتظهر للمستخدمين، وبتضل محفوظة لدى الصفحة.",
            reply_markup=client_main_keyboard(),
        )
        return END
    if data == "client:menu":
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
    await update.effective_message.reply_text(
        "🌸 استخدم الأزرار الموجودة بالقائمة.",
        reply_markup=client_main_keyboard(),
    )
    return END


async def _run_search(update: Any, context: Any, text: str) -> int:
    base = parse_search_text(text)
    if not any((
        base.gender, base.province, base.city, base.age_min, base.age_max,
        base.marital_status, base.occupation,
    )):
        message = "⚠️ ما قدرت أفهم فلاتر البحث. اكتب مثلاً: بنت من دمشق بين 22 و27 سنة عزباء"
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.effective_message.reply_text(message)
        return END

    filters = base
    ai = context.application.bot_data["ai_service"]
    if ai.is_configured:
        try:
            ai_filters = filters_from_ai(await ai.parse_search_filters(text), text)
            filters = merge_filters(base, ai_filters)
        except Exception:
            filters = base

    with _session(context) as session:
        rows = ProfileRepository(session).search(filters)
    context.user_data.pop("client_flow", None)

    if not rows:
        await update.effective_message.reply_text(
            "🔎 ما لقينا عروض مطابقة لهالمواصفات. جرّب وسّع البحث شوي.",
            reply_markup=client_main_keyboard(),
        )
        return END

    await update.effective_message.reply_text(
        f"💗 لقينا {len(rows)} عرض مناسب مبدئياً.\n\n"
        + "\n".join(
            f"📌 طلب {row.request_number} — {row.age} سنة — {row.province}"
            + (f" - {row.city}" if row.city else "")
            for row in rows
        ),
        reply_markup=client_results_keyboard([row.request_number for row in rows]),
    )
    return END


async def _show_latest(update: Any, context: Any) -> None:
    with _session(context) as session:
        rows = ProfileRepository(session).latest(10)
    if not rows:
        await update.callback_query.edit_message_text(
            "📋 ما في عروض متاحة حالياً.",
            reply_markup=client_main_keyboard(),
        )
        return
    await update.callback_query.edit_message_text(
        "📋 أحدث العروض:\n\n" + "\n".join(
            f"📌 طلب {row.request_number} — {row.age} سنة — {row.province}"
            + (f" - {row.city}" if row.city else "")
            for row in rows
        ),
        reply_markup=client_results_keyboard([row.request_number for row in rows]),
    )


async def _show_profile(update: Any, context: Any, request_number: int | None) -> int:
    if request_number is None:
        return END
    with _session(context) as session:
        public = ProfileRepository(session).get_public(request_number)
        if public is None or public.get("status") != "active":
            await update.callback_query.edit_message_text(
                "❌ ما عاد هالعرض متاح.",
                reply_markup=client_main_keyboard(),
            )
            return END
    await update.callback_query.edit_message_text(
        format_public(public),
        reply_markup=client_profile_keyboard(request_number),
    )
    return END


async def _create_contact_order(update: Any, context: Any, request_number: int | None) -> int:
    if request_number is None:
        return END
    user = update.effective_user
    with _session(context) as session:
        repo = OrderRepository(session)
        order = repo.create_contact_request(user.id, request_number, Decimal("5.00"), "شام كاش")
        if order is None:
            await update.callback_query.edit_message_text(
                "❌ ما قدرنا ننشئ الطلب، يمكن العرض ما عاد متاح.",
                reply_markup=client_main_keyboard(),
            )
            return END
        session.commit()
        number = order.order_number

    context.user_data["client_flow"] = "payment"
    context.user_data["pending_order_number"] = number
    account = _settings(context).cham_cash_account
    payment_line = f"\nحساب الدفع: {account}" if account else ""
    await update.callback_query.edit_message_text(
        f"📩 تم إنشاء طلب التواصل رقم {number}.\n\n"
        "💵 قيمة الخدمة: 5 دولار\n"
        f"💳 طريقة الدفع: شام كاش{payment_line}\n\n"
        "حوّل المبلغ بالطريقة المعتمدة، وبعدها ابعت رقم العملية برسالة وحدة هون.\n\n"
        "🔒 بيانات التواصل الخاصة ما بتظهر للمستخدم، وبتضل لدى الصفحة."
    )
    await _notify_admins(context, number, user.id, request_number)
    return PAYMENT_TX


async def _save_transaction(update: Any, context: Any, text: str) -> int:
    order_number = context.user_data.get("pending_order_number")
    if not order_number:
        return END
    with _session(context) as session:
        repo = OrderRepository(session)
        order = repo.get(order_number)
        if order is None or order.user_telegram_id != update.effective_user.id:
            await update.effective_message.reply_text(
                "❌ ما لقينا طلب الدفع.",
                reply_markup=client_main_keyboard(),
            )
            return END
        repo.set_transaction_id(order_number, text)
        session.commit()

    context.user_data.pop("client_flow", None)
    context.user_data.pop("pending_order_number", None)
    await update.effective_message.reply_text(
        f"✅ تم تسجيل رقم العملية للطلب {order_number}.\nرح تراجعها الصفحة يدوياً، وبعدها بينتواصلوا معك.",
        reply_markup=client_main_keyboard(),
    )
    return END


async def _notify_admins(context: Any, order_number: int, user_id: int, profile_request: int) -> None:
    for admin_id in _settings(context).admin_user_ids:
        try:
            await context.application.bot.send_message(
                admin_id,
                f"💳 طلب تواصل جديد\nطلب الدفع: {order_number}\nTelegram User ID: {user_id}\nالإعلان: {profile_request}\nالقيمة: 5 USD",
            )
        except Exception:
            pass


def format_public(profile: dict) -> str:
    from app.services.profiles import format_client_profile
    return format_client_profile(profile)


def _number_suffix(data: str) -> int | None:
    try:
        return int(data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None
