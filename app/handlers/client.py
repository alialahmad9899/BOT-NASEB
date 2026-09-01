"""Client-facing browsing and natural-language search flow."""

from __future__ import annotations

from typing import Any

from app.database.repositories import ProfileFilters, ProfileRepository, OrderRepository
from app.keyboards.client import (
    client_main_keyboard,
    client_no_results_keyboard,
    client_order_detail_keyboard,
    client_orders_keyboard,
    client_profile_keyboard,
    client_results_keyboard,
    client_search_confirm_keyboard,
    client_search_keyboard,
)
from app.services.profiles import format_client_profile, mask_phone
from app.services.search import filters_from_ai, merge_filters, parse_search_text

END = -1
SEARCH_TEXT = 30
SEARCH_CONFIRM = 32


def next_search_state(has_valid_filters: bool) -> int:
    return SEARCH_CONFIRM if has_valid_filters else SEARCH_TEXT


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _has_filters(filters: ProfileFilters) -> bool:
    return any((
        filters.gender,
        filters.residence,
        filters.age_min,
        filters.age_max,
        filters.marital_status,
        filters.occupation,
        filters.education,
        filters.children_min is not None,
        filters.children_max is not None,
    ))


def _target_gender_label(target_gender: str | None) -> str:
    if target_gender == "female":
        return "👰 عروس"
    if target_gender == "male":
        return "🤵 عريس"
    return ""


def _search_prompt(target_gender: str | None = None) -> str:
    if target_gender == "female":
        return (
            "👰 تمام ❤️\n\n"
            "اكتبلي شو المواصفات اللي بتدور عليها\n"
            "وبأي طريقة بتحب.\n\n"
            "مثلاً:\n\n"
            "بدي بنت من دمشق\n"
            "عمرها بين 22 و28\n"
            "عزباء وما عندها ولاد\n"
            "وتكون موظفة\n\n"
            "أو اكتبها بطريقتك العادية، وأنا بفهم عليك.\n\n"
            "✍️ اكتب طلبك:"
        )
    if target_gender == "male":
        return (
            "🤵 تمام ❤️\n\n"
            "اكتبلي شو المواصفات اللي بتدور عليها.\n\n"
            "مثلاً:\n\n"
            "بدي شب من دمشق\n"
            "عمره بين 28 و35\n"
            "ما بدخن\n"
            "ويكون جدي بالزواج\n\n"
            "أو اكتبها بطريقتك العادية، وأنا بفهم عليك.\n\n"
            "✍️ اكتب طلبك:"
        )
    return (
        "🔎 تمام ❤️\n\n"
        "اكتبلي شو المواصفات اللي بتدور عليها، وبأي طريقة بتحب.\n\n"
        "اكتبها بطريقتك العادية، وأنا بفهم عليك.\n\n"
        "✍️ اكتب طلبك:"
    )


def _filters_summary(filters: ProfileFilters) -> str:
    lines = ["🧠 فهمت عليك هيك:"]
    if filters.gender:
        lines.append(f"{_target_gender_label(filters.gender)} بدك")
    if filters.residence:
        lines.append(f"📍 السكن: {filters.residence}")
    if filters.age_min is not None and filters.age_max is not None:
        if filters.age_min == filters.age_max:
            lines.append(f"🎂 العمر: {filters.age_min} سنة")
        else:
            lines.append(f"🎂 العمر: {filters.age_min} إلى {filters.age_max} سنة")
    elif filters.age_min is not None:
        lines.append(f"🎂 العمر: من {filters.age_min} سنة وفوق")
    elif filters.age_max is not None:
        lines.append(f"🎂 العمر: حتى {filters.age_max} سنة")
    if filters.marital_status:
        lines.append(f"💍 الحالة الاجتماعية: {filters.marital_status}")
    if filters.children_min == 0 and filters.children_max == 0:
        lines.append("👶 بدون أولاد")
    elif filters.children_min is not None or filters.children_max is not None:
        child_min = filters.children_min if filters.children_min is not None else 0
        if filters.children_max is not None and filters.children_max != child_min:
            lines.append(f"👶 عدد الأولاد: من {child_min} إلى {filters.children_max}")
        else:
            lines.append(f"👶 عدد الأولاد: {child_min}")
    if filters.occupation:
        lines.append(f"💼 العمل: {filters.occupation}")
    if filters.education:
        lines.append(f"📚 التعليم: {filters.education}")
    return "\n".join(lines)


def _result_text(rows) -> str:
    blocks = []
    for row in rows:
        gender_icon = "👩" if row.gender == "female" else "🤵"
        status_line = "\n🔒 العرض محجوز حالياً" if row.status == "reserved" else ""
        blocks.append(
            "\n".join([
                f"📌 طلب {row.request_number}",
                f"{gender_icon} العمر: {row.age} سنة",
                f"📍 السكن: {row.residence}",
                f"💍 الحالة: {row.marital_status or 'غير محددة'}",
            ]) + status_line
        )
    return f"❤️ لقينا {len(rows)} عروض مناسبة\n\n" + "\n\n".join(blocks)


def _broaden_filters(filters: ProfileFilters) -> ProfileFilters:
    age_min = max(18, filters.age_min - 3) if filters.age_min is not None else None
    age_max = min(100, filters.age_max + 3) if filters.age_max is not None else None
    return ProfileFilters(
        gender=filters.gender,
        residence=None,
        age_min=age_min,
        age_max=age_max,
        marital_status=None,
        occupation=filters.occupation,
        education=filters.education,
        children_min=None,
        children_max=None,
        limit=filters.limit,
    )


def _order_status_label(status: str | None) -> str:
    return {
        "pending_payment": "🟠 بانتظار التواصل",
        "pending_review": "🟠 قيد المتابعة",
        "paid": "✅ مكتمل",
        "rejected": "❌ مرفوض",
    }.get(status or "", "🟠 قيد المتابعة")


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

    if data == "client:search:broaden":
        filters = context.user_data.get("pending_search_filters")
        if not isinstance(filters, ProfileFilters):
            context.user_data.clear()
            await query.edit_message_text("🔎 بلّش بحث جديد واكتبلي المواصفات بطريقتك.", reply_markup=client_main_keyboard())
            return END
        broadened = _broaden_filters(filters)
        if broadened == filters:
            await query.edit_message_text("💛 ما قدرنا نوسّع البحث أكتر. جرّب تعدّل المواصفات شوي.", reply_markup=client_no_results_keyboard())
            return END
        context.user_data["pending_search_filters"] = broadened
        return await _execute_pending_search(update, context)

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

    if data == "client:about":
        context.user_data.clear()
        await query.edit_message_text(
            "ℹ️ كيف بتشتغل لقاء ونصيب؟\n\n"
            "1️⃣ اختار إذا بدك عروس أو عريس.\n"
            "2️⃣ اكتب المواصفات بطريقتك.\n"
            "3️⃣ منبحث بين عروض الصفحة.\n"
            "4️⃣ إذا عجبك عرض، اطلب التواصل.\n"
            "5️⃣ الخطّابة بتتواصل معك وبتشرحلك طريقة الدفع.\n\n"
            "🔒 معلومات التواصل خاصة وما بتظهر للعامة.",
            reply_markup=client_main_keyboard(),
        )
        return END

    if data == "client:menu":
        context.user_data.clear()
        await query.edit_message_text(
            "🌸 القائمة الرئيسية\n\nشو حابب تعمل؟",
            reply_markup=client_main_keyboard(),
        )
        return END

    if data.startswith("client:profile:"):
        return await _show_profile(update, context, _number_suffix(data))

    return END


async def client_text(update: Any, context: Any) -> int:
    text = (update.effective_message.text or "").strip()
    if context.user_data.get("client_flow") == "search":
        return await _run_search(update, context, text)
    await update.effective_message.reply_text(
        "🌸 اختار الخدمة اللي بدك ياها من القائمة.",
        reply_markup=client_main_keyboard(),
    )
    return END


async def _run_search(update: Any, context: Any, text: str) -> int:
    base = parse_search_text(text)
    target_gender = context.user_data.get("search_target_gender")
    if target_gender in {"male", "female"}:
        base = ProfileFilters(
            gender=target_gender,
            residence=base.residence,
            age_min=base.age_min,
            age_max=base.age_max,
            marital_status=base.marital_status,
            occupation=base.occupation,
            education=base.education,
            children_min=base.children_min,
            children_max=base.children_max,
            limit=base.limit,
        )

    filters = base
    ai = context.application.bot_data["ai_service"]
    if ai.is_configured:
        try:
            ai_filters = filters_from_ai(await ai.parse_search_filters(text), text)
            if target_gender in {"male", "female"}:
                ai_filters = ProfileFilters(
                    gender=target_gender,
                    residence=ai_filters.residence,
                    age_min=ai_filters.age_min,
                    age_max=ai_filters.age_max,
                    marital_status=ai_filters.marital_status,
                    occupation=ai_filters.occupation,
                    education=ai_filters.education,
                    children_min=ai_filters.children_min,
                    children_max=ai_filters.children_max,
                    limit=ai_filters.limit,
                )
            filters = merge_filters(base, ai_filters)
        except Exception:
            pass

    if not _has_filters(filters):
        await update.effective_message.reply_text(
            "⚠️ ما قدرت أفهم طلبك بشكل كافي.\n\nجرّب تكتب مثلاً: بدي بنت من دمشق بين 22 و28 سنة عزباء.",
            reply_markup=client_search_keyboard(),
        )
        return SEARCH_TEXT

    context.user_data["pending_search_filters"] = filters
    context.user_data["pending_search_text"] = text
    await update.effective_message.reply_text(
        _filters_summary(filters) + "\n\nهي المواصفات صحيحة؟",
        reply_markup=client_search_confirm_keyboard(),
    )
    return SEARCH_CONFIRM


async def _execute_pending_search(update: Any, context: Any) -> int:
    filters = context.user_data.get("pending_search_filters")
    if not isinstance(filters, ProfileFilters):
        await update.callback_query.edit_message_text(
            "❌ ما عاد في طلب بحث جاهز. بلّش بحث جديد.",
            reply_markup=client_main_keyboard(),
        )
        return END

    with _session(context) as session:
        rows = ProfileRepository(session).search(filters)

    request_numbers = [row.request_number for row in rows]
    if not rows:
        context.user_data["last_result_numbers"] = []
        await update.callback_query.edit_message_text(
            "💛 للأسف ما لقينا عرض مطابق تماماً لهالمواصفات.\n\n"
            "بس فينا نوسّع البحث شوي.\n\n"
            "• نوسّع العمر\n"
            "• نوسّع مكان السكن\n"
            "• نشيل شرط معين\n\n"
            "شو بتحب نعمل؟",
            reply_markup=client_no_results_keyboard(),
        )
        return END

    context.user_data["last_result_numbers"] = request_numbers
    await update.callback_query.edit_message_text(
        _result_text(rows),
        reply_markup=client_results_keyboard(request_numbers),
    )
    return END


async def _show_saved_results(update: Any, context: Any) -> int:
    numbers = context.user_data.get("last_result_numbers") or []
    if not numbers:
        await update.callback_query.edit_message_text(
            "🔎 ما في نتائج محفوظة حالياً. بلّش بحث جديد.",
            reply_markup=client_main_keyboard(),
        )
        return END

    with _session(context) as session:
        rows = [
            row for number in numbers
            if (row := ProfileRepository(session).get(number)) is not None
            and row.status != "inactive"
        ]

    if not rows:
        context.user_data.clear()
        await update.callback_query.edit_message_text(
            "🔎 ما عاد في نتائج متاحة من البحث السابق.",
            reply_markup=client_main_keyboard(),
        )
        return END

    context.user_data["last_result_numbers"] = [row.request_number for row in rows]
    await update.callback_query.edit_message_text(
        _result_text(rows),
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

    context.user_data["last_result_numbers"] = [row.request_number for row in rows]
    await update.callback_query.edit_message_text(
        _result_text(rows),
        reply_markup=client_results_keyboard([row.request_number for row in rows]),
    )


async def _show_orders(update: Any, context: Any) -> int:
    user_id = update.effective_user.id
    with _session(context) as session:
        orders = OrderRepository(session).list_for_user(user_id)
    if not orders:
        await update.callback_query.edit_message_text(
            "💳 ما عندك طلبات تواصل حالياً.",
            reply_markup=client_main_keyboard(),
        )
        return END

    blocks = []
    for order in orders:
        whatsapp = order.whatsapp or "غير مسجل"
        blocks.append(
            "\n".join([
                f"📌 طلب {order.order_number}",
                f"💍 الإعلان: {order.profile.request_number}",
                _order_status_label(order.status),
                f"📱 واتساب: {whatsapp}",
            ])
        )
    await update.callback_query.edit_message_text(
        "💳 طلباتي\n\n" + "\n\n".join(blocks),
        reply_markup=client_orders_keyboard([order.order_number for order in orders]),
    )
    return END


async def _show_order(update: Any, context: Any, order_number: int | None) -> int:
    if order_number is None:
        return END
    with _session(context) as session:
        order = OrderRepository(session).get(order_number)
    if order is None or order.user_telegram_id != update.effective_user.id:
        await update.callback_query.edit_message_text(
            "❌ ما لقينا هالطلب ضمن طلباتك.",
            reply_markup=client_main_keyboard(),
        )
        return END

    message = "\n".join([
        "📩 تفاصيل طلب التواصل",
        "",
        f"📌 رقم الطلب: {order.order_number}",
        f"💍 الإعلان: {order.profile.request_number}",
        f"💵 قيمة الخدمة: {order.amount_usd} دولار",
        f"💳 طريقة الدفع: {order.payment_method}",
        f"📱 واتساب: {order.whatsapp or 'غير مسجل'}",
        _order_status_label(order.status),
    ])
    await update.callback_query.edit_message_text(
        message,
        reply_markup=client_order_detail_keyboard(order.status, order.order_number),
    )
    return END


async def _show_profile(update: Any, context: Any, request_number: int | None) -> int:
    if request_number is None:
        return END
    with _session(context) as session:
        repo = ProfileRepository(session)
        public = repo.get_public(request_number)
        contact = repo.get_contact(request_number)
    if public is None or public.get("status") == "inactive":
        await update.callback_query.edit_message_text(
            "❌ ما عاد هالعرض متاح.",
            reply_markup=client_main_keyboard(),
        )
        return END

    masked = mask_phone(contact.phone) if contact and contact.phone else None
    has_results = bool(context.user_data.get("last_result_numbers"))
    await update.callback_query.edit_message_text(
        format_client_profile(public, masked_phone=masked),
        reply_markup=client_profile_keyboard(
            request_number,
            public.get("status", "active"),
            has_results=has_results,
        ),
    )
    return END


def _number_suffix(data: str | None) -> int | None:
    if not data:
        return None
    try:
        return int(data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None
