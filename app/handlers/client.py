"""Client-facing browsing, natural-language search, orders, and manual payment flow."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.database.repositories import OrderRepository, ProfileFilters, ProfileRepository
from app.keyboards.client import (
    client_main_keyboard,
    client_no_results_keyboard,
    client_order_detail_keyboard,
    client_orders_keyboard,
    client_payment_keyboard,
    client_profile_keyboard,
    client_results_history_keyboard,
    client_results_keyboard,
    client_search_confirm_keyboard,
    client_search_keyboard,
)
from app.services.profiles import format_client_profile, mask_phone
from app.services.search import filters_from_ai, merge_filters, parse_search_text

END = -1
SEARCH_TEXT = 30
PAYMENT_TX = 31
SEARCH_CONFIRM = 32


def next_search_state(has_valid_filters: bool) -> int:
    return SEARCH_CONFIRM if has_valid_filters else SEARCH_TEXT


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
        return "🤵 دورولي على عريس مناسب\n\nاكتب المواصفات متل ما بتحكي عادة، وما في داعي لترتيب معين.\nمثلاً: بدي عريس من دمشق عمره بين 28 و35 وما بدخن.\n\nرح أفهم طلبك أولاً وبعدها فرجيك شو فهمت قبل ما أعمل البحث."
    if target_gender == "female":
        return "👰 دورولي على عروس مناسبة\n\nاكتب المواصفات متل ما بتحكي عادة، وما في داعي لترتيب معين.\nمثلاً: بدي بنت من الشام عمرها بين 22 و28 ومطلقة بدون ولاد.\n\nرح أفهم طلبك أولاً وبعدها فرجيك شو فهمت قبل ما أعمل البحث."
    return "🔎 اكتب طلب البحث بطريقتك\n\nما في داعي تلتزم بصيغة محددة؛ احكي عادي وأنا بفهم المقصود.\nمثلاً: بدي بنت من حمص عمرها حوالي 25، أو بدي عريس ساكن بريف حماة.\n\nرح فرجيك شو فهمت قبل ما أطلع النتائج."


def _filters_summary(filters: ProfileFilters) -> str:
    lines = ["🧠 فهمت طلبك هيك:"]
    if filters.gender:
        lines.append(f"👤 النوع: {'بنت/عروس' if filters.gender == 'female' else 'شاب/عريس'}")
    if filters.residence:
        lines.append(f"📍 السكن: {filters.residence}")
    if filters.age_min is not None and filters.age_max is not None:
        if filters.age_min == filters.age_max:
            lines.append(f"🎂 العمر: {filters.age_min} سنة")
        else:
            lines.append(f"🎂 العمر: من {filters.age_min} إلى {filters.age_max} سنة")
    elif filters.age_min is not None:
        lines.append(f"🎂 العمر: من {filters.age_min} سنة وفوق")
    elif filters.age_max is not None:
        lines.append(f"🎂 العمر: حتى {filters.age_max} سنة")
    if filters.marital_status:
        lines.append(f"💍 الحالة الاجتماعية: {filters.marital_status}")
    if filters.children_min == 0 and filters.children_max == 0:
        lines.append("👶 بدون أولاد")
    elif filters.children_min is not None or filters.children_max is not None:
        child_text = filters.children_min if filters.children_min is not None else 0
        if filters.children_max is not None and filters.children_max != child_text:
            lines.append(f"👶 عدد الأولاد: من {child_text} إلى {filters.children_max}")
        else:
            lines.append(f"👶 عدد الأولاد: {child_text}")
    if filters.occupation:
        lines.append(f"💼 العمل: {filters.occupation}")
    if filters.education:
        lines.append(f"📚 التعليم: {filters.education}")
    return "\n".join(lines)


def _result_text(rows) -> str:
    return "💗 لقينا {} عرض مناسب مبدئياً.\n\n{}".format(
        len(rows),
        "\n".join(
            f"📌 طلب {row.request_number} — {row.age} سنة — {row.residence} — {('🔒 محجوز' if row.status == 'reserved' else '✅ متاح')}"
            for row in rows
        ),
    )


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
    if data == "client:search:execute":
        return await _execute_pending_search(update, context)
    if data == "client:search:edit":
        target_gender = context.user_data.get("search_target_gender")
        context.user_data.clear()
        context.user_data["client_flow"] = "search"
        if target_gender in {"male", "female"}:
            context.user_data["search_target_gender"] = target_gender
        await query.edit_message_text(_search_prompt(target_gender), reply_markup=client_search_keyboard())
        return SEARCH_TEXT
    if data == "client:results":
        return await _show_saved_results(update, context)
    if data == "client:list":
        context.user_data.clear()
        await _show_latest(update, context)
        return END
    if data == "client:orders":
        context.user_data.clear()
        return await _show_orders(update, context)
    if data.startswith("client:order:view:"):
        return await _show_order(update, context, _number_suffix(data))
    if data == "client:payment:submit":
        if not context.user_data.get("pending_order_number"):
            await query.edit_message_text("❌ ما في طلب دفع مفتوح حالياً. فيك تشوف طلباتك من القائمة.", reply_markup=client_main_keyboard())
            return END
        await query.edit_message_text("🧾 تمام، ابعت رقم عملية التحويل برسالة وحدة.", reply_markup=client_search_keyboard())
        return PAYMENT_TX
    if data == "client:payment:cancel":
        order_number = context.user_data.get("pending_order_number")
        context.user_data.clear()
        suffix = f" للطلب {order_number}" if order_number else ""
        await query.edit_message_text(f"✅ تم إلغاء إدخال رقم العملية{suffix}. الطلب ما زال محفوظاً ضمن طلباتك.", reply_markup=client_main_keyboard())
        return END
    if data == "client:about":
        context.user_data.clear()
        await query.edit_message_text("ℹ️ طريقة العمل\n\nفيك تتصفح عروض الزواج أو تكتب طلبك بطريقتك العادية، حتى لو كان قصير أو عامي.\n\n🧠 Gemini بيفهم الطلب وبيحوّله لفلاتر بحث، وبعدها قاعدة البيانات هي اللي بتطلع النتائج.\n\n🔒 معلومات التواصل الخاصة ما بتظهر مكشوفة للمستخدم.\n\n💳 طلب التواصل مدفوع بقيمة 5 دولار عبر شام كاش، وبعد تسجيل الطلب بتتواصل معك الخطابة لتشرحلك طريقة الدفع.", reply_markup=client_main_keyboard())
        return END
    if data == "client:menu":
        context.user_data.clear()
        await query.edit_message_text("🌸 القائمة الرئيسية\n\nاختر الخدمة اللي بدك ياها:", reply_markup=client_main_keyboard())
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
    context.user_data["pending_search_filters"] = filters
    context.user_data["pending_search_text"] = text
    summary = _filters_summary(filters)
    if ai_error:
        summary += "\n\n⚠️ تم الاعتماد على المعلومات الواضحة من طلبك فقط لأن Gemini غير متاح حالياً."
    summary += "\n\nإذا هاد اللي قصدته، اضغط «ابحث»."
    await update.effective_message.reply_text(summary, reply_markup=client_search_confirm_keyboard())
    return SEARCH_CONFIRM


async def _execute_pending_search(update: Any, context: Any) -> int:
    filters = context.user_data.get("pending_search_filters")
    if not isinstance(filters, ProfileFilters):
        await update.callback_query.edit_message_text("❌ ما عاد في طلب بحث جاهز. بلّش بحث جديد.", reply_markup=client_main_keyboard())
        return END
    with _session(context) as session:
        rows = ProfileRepository(session).search(filters)
    request_numbers = [row.request_number for row in rows]
    if not rows:
        context.user_data.clear()
        await update.callback_query.edit_message_text("🔎 ما لقينا عروض مطابقة لهالمواصفات. فيك تخفف شرط أو توسّع العمر أو مكان السكن.", reply_markup=client_no_results_keyboard())
        return END
    context.user_data["last_result_numbers"] = request_numbers
    await update.callback_query.edit_message_text(_result_text(rows), reply_markup=client_results_keyboard(request_numbers))
    return END


async def _show_saved_results(update: Any, context: Any) -> int:
    numbers = context.user_data.get("last_result_numbers") or []
    if not numbers:
        await update.callback_query.edit_message_text("🔎 ما في نتائج محفوظة حالياً. بلّش بحث جديد.", reply_markup=client_main_keyboard())
        return END
    with _session(context) as session:
        rows = [row for number in numbers if (row := ProfileRepository(session).get(number)) is not None and row.status != "inactive"]
    if not rows:
        context.user_data.clear()
        await update.callback_query.edit_message_text("🔎 ما عاد في نتائج متاحة من البحث السابق.", reply_markup=client_main_keyboard())
        return END
    context.user_data["last_result_numbers"] = [row.request_number for row in rows]
    await update.callback_query.edit_message_text(_result_text(rows), reply_markup=client_results_keyboard([row.request_number for row in rows]))
    return END


async def _show_latest(update: Any, context: Any) -> None:
    with _session(context) as session:
        rows = ProfileRepository(session).latest(10)
    if not rows:
        await update.callback_query.edit_message_text("📋 ما في عروض متاحة حالياً.", reply_markup=client_main_keyboard())
        return
    context.user_data["last_result_numbers"] = [row.request_number for row in rows]
    await update.callback_query.edit_message_text(
        "📋 أحدث العروض:\n\n" + "\n".join(
            f"📌 طلب {row.request_number} — {row.age} سنة — {row.residence} — {('🔒 محجوز' if row.status == 'reserved' else '✅ متاح')}"
            for row in rows
        ),
        reply_markup=client_results_keyboard([row.request_number for row in rows]),
    )


async def _show_orders(update: Any, context: Any) -> int:
    user_id = update.effective_user.id
    with _session(context) as session:
        orders = OrderRepository(session).list_for_user(user_id)
    if not orders:
        await update.callback_query.edit_message_text("💳 ما عندك طلبات تواصل حالياً.", reply_markup=client_main_keyboard())
        return END
    status_labels = {
        "pending_payment": "بانتظار الدفع",
        "pending_review": "بانتظار مراجعة الدفع",
        "paid": "تم تأكيد الدفع",
        "rejected": "مرفوض",
    }
    text = "💳 طلبات التواصل الخاصة فيك:\n\n" + "\n".join(
        f"📌 طلب {order.order_number} — الإعلان {order.profile.request_number} — {status_labels.get(order.status, order.status)}"
        for order in orders
    )
    await update.callback_query.edit_message_text(text, reply_markup=client_orders_keyboard([order.order_number for order in orders]))
    return END


async def _show_order(update: Any, context: Any, order_number: int | None) -> int:
    if order_number is None:
        return END
    with _session(context) as session:
        order = OrderRepository(session).get(order_number)
    if order is None or order.user_telegram_id != update.effective_user.id:
        await update.callback_query.edit_message_text("❌ ما لقينا هالطلب ضمن طلباتك.", reply_markup=client_main_keyboard())
        return END
    status_labels = {
        "pending_payment": "بانتظار الدفع",
        "pending_review": "بانتظار مراجعة الدفع",
        "paid": "تم تأكيد الدفع",
        "rejected": "مرفوض",
    }
    transaction = order.transaction_id or "لم يُرسل بعد"
    message = (
        f"💳 تفاصيل طلب التواصل {order.order_number}\n\n"
        f"📌 الإعلان: {order.profile.request_number}\n"
        f"💵 المبلغ: {order.amount_usd} دولار\n"
        f"💳 طريقة الدفع: {order.payment_method}\n"
        f"🧾 رقم العملية: {transaction}\n"
        f"📊 الحالة: {status_labels.get(order.status, order.status)}"
    )
    await update.callback_query.edit_message_text(message, reply_markup=client_order_detail_keyboard())
    return END


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
    has_results = bool(context.user_data.get("last_result_numbers"))
    await update.callback_query.edit_message_text(format_client_profile(public, masked_phone=masked), reply_markup=client_profile_keyboard(request_number, public.get("status", "active"), has_results=has_results))
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
    account = _settings(context).cham_cash_account
    payment_lines = [
        f"📩 طلب التواصل رقم {number}",
        "",
        "💵 قيمة الخدمة: 5 دولار",
        "💳 الدفع: شام كاش",
    ]
    if account:
        payment_lines.extend([f"📱 حساب شام كاش: {account}"])
    payment_lines.extend([
        "",
        "بعد تجهيز التحويل، اضغط «إدخال رقم العملية» وابعت رقم العملية برسالة وحدة.",
        "رح تتواصل معك الخطابة على حسابك هون لمتابعة الطلب.",
    ])
    await update.callback_query.edit_message_text("\n".join(payment_lines), reply_markup=client_payment_keyboard())
    await _notify_admins(context, number, user, request_number)
    return PAYMENT_TX


async def _save_transaction(update: Any, context: Any, text: str) -> int:
    order_number = context.user_data.get("pending_order_number")
    transaction_id = text.strip()
    if not order_number or not transaction_id:
        await update.effective_message.reply_text("🧾 ابعت رقم عملية التحويل برسالة وحدة.", reply_markup=client_search_keyboard())
        return PAYMENT_TX
    with _session(context) as session:
        repo = OrderRepository(session)
        order = repo.get(order_number)
        if order is None or order.user_telegram_id != update.effective_user.id:
            await update.effective_message.reply_text("❌ ما لقينا طلب الدفع.", reply_markup=client_main_keyboard())
            return END
        updated = repo.set_transaction_id(order_number, transaction_id)
        if updated is None:
            await update.effective_message.reply_text("❌ ما قدرنا نسجل رقم العملية.", reply_markup=client_main_keyboard())
            return END
        session.commit()
    context.user_data.clear()
    await update.effective_message.reply_text(f"✅ تم تسجيل رقم العملية للطلب {order_number}. رح تراجعه الصفحة يدوياً.", reply_markup=client_main_keyboard())
    await _notify_payment_update(context, order_number, update.effective_user.id, transaction_id)
    return END


async def _notify_admins(context: Any, order_number: int, user: Any, profile_request: int) -> None:
    username = f"@{user.username}" if getattr(user, "username", None) else "بدون Username"
    display_name = " ".join(part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part) or "بدون اسم"
    for admin_id in _settings(context).admin_user_ids:
        try:
            await context.application.bot.send_message(admin_id, "💳 طلب تواصل جديد\n\n" f"📌 طلب الدفع: {order_number}\n" f"📌 الإعلان المطلوب: {profile_request}\n" "💵 القيمة: 5 USD\n\n" f"👤 اسم حساب العميل: {display_name}\n" f"🔹 Username: {username}\n" f"🆔 Telegram User ID: {user.id}\n\n" "📞 تواصلوا معه لشرح طريقة الدفع ومتابعة الطلب.")
        except Exception:
            pass


async def _notify_payment_update(context: Any, order_number: int, user_id: int, transaction_id: str) -> None:
    for admin_id in _settings(context).admin_user_ids:
        try:
            await context.application.bot.send_message(admin_id, "🧾 تم إرسال رقم عملية دفع\n\n" f"📌 طلب الدفع: {order_number}\n" f"🆔 Telegram User ID: {user_id}\n" f"🧾 رقم العملية: {transaction_id}\n\n" "🔎 الطلب جاهز للمراجعة والتأكيد.")
        except Exception:
            pass


def _number_suffix(data: str | None) -> int | None:
    if not data:
        return None
    try:
        return int(data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None
