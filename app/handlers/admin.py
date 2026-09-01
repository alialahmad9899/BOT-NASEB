"""Administrative Telegram flows with defense-in-depth authorization."""

from __future__ import annotations

import json
import re
from typing import Any

from app.database.repositories import OrderRepository, ProfileRepository, export_all_data, profile_to_dict
from app.services.ai import AIExtractionError, AIService, ProfileExtraction, basic_profile_extraction
from app.services.permissions import is_admin
from app.services.profiles import ProfileDraft, apply_text_edits, extraction_to_draft, format_admin_profile, format_draft_preview, validate_profile_extraction
from app.services.search import filters_from_ai, merge_filters, parse_search_text

END = -1
ADD_RAW = 10
ADD_EDIT = 11
SEARCH_TEXT = 12
EDIT_REQUEST = 13
EDIT_FIELDS = 14
DISABLE_REQUEST = 15
DELETE_REQUEST = 16


def _admin_main_keyboard():
    from app.keyboards.admin import admin_main_keyboard
    return admin_main_keyboard()


def _back_to_admin_keyboard():
    from app.keyboards.admin import back_to_admin_keyboard
    return back_to_admin_keyboard()


def _add_preview_keyboard(can_save: bool = True):
    from app.keyboards.admin import add_preview_keyboard
    return add_preview_keyboard(can_save)


def _confirm_disable_keyboard(request_number: int):
    from app.keyboards.admin import confirm_disable_keyboard
    return confirm_disable_keyboard(request_number)


def _profile_actions_keyboard(request_number: int, status: str = "active"):
    from app.keyboards.admin import profile_actions_keyboard
    return profile_actions_keyboard(request_number, status)


def _order_actions_keyboard(order_number: int):
    from app.keyboards.admin import order_actions_keyboard
    return order_actions_keyboard(order_number)


def _confirm_delete_all_keyboard():
    from app.keyboards.admin import confirm_delete_all_keyboard
    return confirm_delete_all_keyboard()


def _confirm_delete_selected_keyboard():
    from app.keyboards.admin import confirm_delete_selected_keyboard
    return confirm_delete_selected_keyboard()


def admin_action_allowed(user_id: int, admin_user_ids: set[int] | frozenset[int]) -> bool:
    return is_admin(user_id, admin_user_ids)


def _settings(context: Any):
    return context.application.bot_data["settings"]


def _is_admin(update: Any, context: Any) -> bool:
    user = update.effective_user
    return bool(user and admin_action_allowed(user.id, _settings(context).admin_user_ids))


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


async def admin_callback(update: Any, context: Any) -> int:
    query = update.callback_query
    if not _is_admin(update, context):
        await query.answer("❌ ما عندك صلاحية لهالعملية.", show_alert=True)
        return END
    await query.answer()
    data = query.data or ""

    if data == "admin:add":
        context.user_data.clear()
        context.user_data["admin_flow"] = "add_raw"
        await query.edit_message_text("✍️ ابعت نص الإعلان الخام برسالة وحدة.\n\nفيك تلصق النص متل ما وصلك، وأنا بخلّيه عرض زواج مرتب بواسطة Gemini.", reply_markup=_back_to_admin_keyboard())
        return ADD_RAW
    if data == "admin:add:save":
        return await _save_pending_profile(update, context)
    if data == "admin:add:edit":
        context.user_data["admin_flow"] = "add_edit"
        await query.edit_message_text("✏️ ابعت التعديلات بالشكل التالي:\nالعمر=25\nمكان السكن=ريف حماة\nعدد الأولاد=0\nرقم الهاتف=09xxxxxxxx", reply_markup=_back_to_admin_keyboard())
        return ADD_EDIT
    if data == "admin:add:cancel":
        context.user_data.clear()
        await query.edit_message_text("✅ تم إلغاء إضافة الإعلان.", reply_markup=_admin_main_keyboard())
        return END

    if data == "admin:list":
        await _show_latest(update, context)
        return END
    if data == "admin:search":
        context.user_data["admin_flow"] = "search"
        await query.edit_message_text("🔎 اكتبلي طلب البحث بطريقتك، وأنا بفهمه بواسطة الذكاء الاصطناعي.\n\nمثال: بدي بنت من دمشق عمرها بين 22 و30 ومطلقة بدون ولاد.", reply_markup=_back_to_admin_keyboard())
        return SEARCH_TEXT
    if data == "admin:edit":
        context.user_data["admin_flow"] = "edit_request"
        await query.edit_message_text("✏️ ابعت رقم الطلب اللي بدك تعدله.", reply_markup=_back_to_admin_keyboard())
        return EDIT_REQUEST
    if data.startswith("admin:edit:"):
        number = _number_suffix(data)
        return await _begin_direct_edit(update, context, number) if number is not None else END

    if data == "admin:disable":
        context.user_data["admin_flow"] = "disable_request"
        await query.edit_message_text("🗑️ ابعت رقم الطلب اللي بدك تعطّله.", reply_markup=_back_to_admin_keyboard())
        return DISABLE_REQUEST
    if data.startswith("admin:disable:confirm:"):
        return await _disable_profile(update, context, _number_suffix(data))
    if data == "admin:disable:cancel":
        await query.edit_message_text("✅ ما صار أي تغيير.", reply_markup=_admin_main_keyboard())
        return END
    if data.startswith("admin:disable:"):
        number = _number_suffix(data)
        if number is None:
            return END
        await query.edit_message_text(f"⚠️ متأكد بدك تعطّل الإعلان رقم {number}؟", reply_markup=_confirm_disable_keyboard(number))
        return DISABLE_REQUEST

    if data == "admin:reservations":
        with _session(context) as session:
            rows = [row for row in ProfileRepository(session).latest(50, include_inactive=True) if row.status == "reserved"]
        if not rows:
            await query.edit_message_text("🔒 ما في عروض محجوزة حالياً.", reply_markup=_admin_main_keyboard())
            return END
        text = "🔒 العروض المحجوزة:\n\n" + "\n".join(f"📌 طلب {row.request_number} — {row.name or 'بدون اسم'} — {row.age} سنة — {row.residence}" for row in rows)
        await query.edit_message_text(text, reply_markup=_admin_main_keyboard())
        return END
    if data.startswith("admin:reserve:"):
        number = _number_suffix(data)
        if number is None:
            return END
        with _session(context) as session:
            profile = ProfileRepository(session).reserve(number)
            if profile is None:
                await query.edit_message_text("❌ ما قدرنا نحجز هالإعلان.", reply_markup=_admin_main_keyboard())
                return END
            session.commit()
        await query.edit_message_text(f"🔒 تم حجز الإعلان رقم {number}.", reply_markup=_admin_main_keyboard())
        return END
    if data.startswith("admin:unreserve:"):
        number = _number_suffix(data)
        if number is None:
            return END
        with _session(context) as session:
            profile = ProfileRepository(session).activate(number)
            if profile is None:
                await query.edit_message_text("❌ ما قدرنا نرجّع هالإعلان لحالة المتاح.", reply_markup=_admin_main_keyboard())
                return END
            session.commit()
        await query.edit_message_text(f"🔓 تم إلغاء حجز الإعلان رقم {number}.", reply_markup=_admin_main_keyboard())
        return END

    if data == "admin:delete":
        context.user_data["admin_flow"] = "delete_request"
        await query.edit_message_text("🧹 حذف إعلانات\n\nاكتب أرقام الطلبات اللي بدك تحذفها، وافصل بينها بفواصل أو مسافات.\nمثال: 101, 104, 108\n\nولحذف الكل استخدم زر «حذف الكل».", reply_markup=_back_to_admin_keyboard())
        return DELETE_REQUEST
    if data == "admin:delete:all":
        await query.edit_message_text("⚠️ انتبه! هالعملية رح تحذف **كل إعلانات الزواج وطلبات التواصل المرتبطة فيها نهائياً**.\n\nمتأكد؟", reply_markup=_confirm_delete_all_keyboard(), parse_mode="Markdown")
        return DELETE_REQUEST
    if data == "admin:delete:all:confirm":
        with _session(context) as session:
            count = ProfileRepository(session).delete_all()
            session.commit()
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم حذف {count} إعلان نهائياً.", reply_markup=_admin_main_keyboard())
        return END
    if data == "admin:delete:selected:confirm":
        numbers = context.user_data.get("delete_numbers") or []
        with _session(context) as session:
            count = ProfileRepository(session).delete_requests(numbers)
            session.commit()
        context.user_data.clear()
        await query.edit_message_text(f"✅ تم حذف {count} إعلان نهائياً.", reply_markup=_admin_main_keyboard())
        return END
    if data == "admin:delete:cancel":
        context.user_data.clear()
        await query.edit_message_text("✅ تم إلغاء الحذف.", reply_markup=_admin_main_keyboard())
        return END
    if data.startswith("admin:delete:one:"):
        number = _number_suffix(data)
        if number is None:
            return END
        context.user_data["delete_numbers"] = [number]
        await query.edit_message_text(f"⚠️ رح ينحذف الإعلان رقم {number} نهائياً مع أي طلبات تواصل مرتبطة فيه.\n\nمتأكد؟", reply_markup=_confirm_delete_selected_keyboard())
        return DELETE_REQUEST

    if data.startswith("admin:profile:"):
        number = _number_suffix(data)
        if number is not None:
            await _show_admin_profile(update, context, number)
        return END
    if data == "admin:stats":
        await _show_stats(update, context)
        return END
    if data == "admin:backup":
        await _send_backup(update, context)
        return END
    if data == "admin:orders":
        await _show_orders(update, context)
        return END
    if data.startswith("admin:order:view:"):
        return await _view_order(update, context, _number_suffix(data))
    if data.startswith("admin:order:confirm:"):
        return await _confirm_order(update, context, _number_suffix(data))
    if data.startswith("admin:order:reject:"):
        return await _reject_order(update, context, _number_suffix(data))
    if data == "admin:menu":
        context.user_data.clear()
        await query.edit_message_text("🔐 لوحة الأدمن", reply_markup=_admin_main_keyboard())
    return END


async def admin_text(update: Any, context: Any) -> int:
    if not _is_admin(update, context):
        await update.effective_message.reply_text("❌ ما عندك صلاحية لهالعملية.")
        return END
    text = (update.effective_message.text or "").strip()
    state = context.user_data.get("admin_flow")
    if state == "add_raw":
        return await _parse_and_preview(update, context, text)
    if state == "add_edit":
        draft = context.user_data.get("pending_profile")
        if not draft:
            await update.effective_message.reply_text("❌ ما في مسودة حالياً. بلّش إضافة إعلان من جديد.", reply_markup=_admin_main_keyboard())
            return END
        context.user_data["pending_profile"] = apply_text_edits(draft, text)
        return await _show_pending_preview(update, context)
    if state == "search":
        return await _run_search(update, context, text)
    if state == "edit_request":
        try:
            number = int(text)
        except ValueError:
            await update.effective_message.reply_text("❌ رقم الطلب لازم يكون رقماً.", reply_markup=_back_to_admin_keyboard())
            return EDIT_REQUEST
        return await _begin_edit_from_message(update, context, number)
    if state == "edit_fields":
        return await _apply_direct_edit(update, context, text)
    if state == "disable_request":
        try:
            number = int(text)
        except ValueError:
            await update.effective_message.reply_text("❌ رقم الطلب لازم يكون رقماً.", reply_markup=_back_to_admin_keyboard())
            return DISABLE_REQUEST
        await update.effective_message.reply_text(f"⚠️ متأكد بدك تعطّل الإعلان رقم {number}؟", reply_markup=_confirm_disable_keyboard(number))
        return DISABLE_REQUEST
    if state == "delete_request":
        if text in {"الكل", "كل", "حذف الكل"}:
            await update.effective_message.reply_text("⚠️ هالعملية رح تحذف كل الإعلانات وطلبات التواصل المرتبطة فيها نهائياً. متأكد؟", reply_markup=_confirm_delete_all_keyboard())
            return DELETE_REQUEST
        raw_numbers = [part for part in re.split(r"[\s,،;]+", text) if part]
        try:
            numbers = sorted({int(part) for part in raw_numbers})
        except ValueError:
            await update.effective_message.reply_text("❌ اكتب أرقام الطلبات فقط، مثلاً: 101, 104, 108", reply_markup=_back_to_admin_keyboard())
            return DELETE_REQUEST
        numbers = [number for number in numbers if number > 0]
        if not numbers:
            await update.effective_message.reply_text("❌ ما وصلني أي رقم طلب صالح.", reply_markup=_back_to_admin_keyboard())
            return DELETE_REQUEST
        with _session(context) as session:
            found = [row for row in (ProfileRepository(session).get(number) for number in numbers) if row is not None]
        if not found:
            await update.effective_message.reply_text("❌ ما لقيت أي إعلان من الأرقام اللي أرسلتها.", reply_markup=_back_to_admin_keyboard())
            return DELETE_REQUEST
        context.user_data["delete_numbers"] = [row.request_number for row in found]
        found_text = "، ".join(str(row.request_number) for row in found)
        await update.effective_message.reply_text(f"⚠️ رح ينحذف نهائياً طلب/طلبات: {found_text}\n\nمتأكد؟", reply_markup=_confirm_delete_selected_keyboard())
        return DELETE_REQUEST
    return END


async def admin_photo(update: Any, context: Any) -> int:
    if not _is_admin(update, context):
        await update.effective_message.reply_text("❌ ما عندك صلاحية لهالعملية.")
        return END
    if context.user_data.get("admin_flow") != "add_raw":
        await update.effective_message.reply_text("📷 الصورة بتنقبل مع نص الإعلان أثناء إضافة إعلان جديد.", reply_markup=_back_to_admin_keyboard())
        return END
    caption = (update.effective_message.caption or "").strip()
    if not caption:
        await update.effective_message.reply_text("✍️ حط نص الإعلان كـ caption للصورة وأعد الإرسال.", reply_markup=_back_to_admin_keyboard())
        return ADD_RAW
    return await _parse_and_preview(update, context, caption, photo_file_id=update.effective_message.photo[-1].file_id)


async def _parse_and_preview(update: Any, context: Any, raw_text: str, photo_file_id: str | None = None) -> int:
    ai: AIService = context.application.bot_data["ai_service"]
    deterministic = basic_profile_extraction(raw_text, photo_file_id)
    if not ai.is_configured:
        await update.effective_message.reply_text("⚠️ Gemini مو مهيأ حالياً، لذلك ما رح أخمّن بيانات الإعلان.", reply_markup=_back_to_admin_keyboard())
        return ADD_RAW
    try:
        extraction = await AIService.resolve_profile_extraction(ai, raw_text, deterministic)
    except AIExtractionError:
        await update.effective_message.reply_text("⚠️ ما قدرت أوصل لـGemini لتنظيم الإعلان. ما تم حفظ أي بيانات.", reply_markup=_back_to_admin_keyboard())
        return ADD_RAW
    if photo_file_id and not extraction.photo_file_id:
        extraction = extraction.model_copy(update={"photo_file_id": photo_file_id})
    context.user_data["pending_profile"] = extraction_to_draft(extraction)
    with _session(context) as session:
        context.user_data["pending_request_number"] = ProfileRepository(session).peek_next_request_number()
    return await _show_pending_preview(update, context, extraction=extraction)


async def _show_pending_preview(update: Any, context: Any, extraction: ProfileExtraction | None = None) -> int:
    draft: ProfileDraft | None = context.user_data.get("pending_profile")
    if draft is None:
        return END
    if extraction is None:
        extraction = ProfileExtraction.model_validate({**draft.public_data, **draft.private_contact_data})
    validation = validate_profile_extraction(extraction, draft.private_contact_data)
    message = format_draft_preview(draft, request_number=context.user_data.get("pending_request_number"))
    labels = {"gender": "النوع", "age": "العمر", "residence": "مكان السكن", "contact": "رقم أو وسيلة تواصل", "children_count": "عدد الأولاد"}
    if validation.missing_fields or validation.errors:
        missing = "، ".join(labels.get(item, item) for item in validation.missing_fields)
        if missing:
            message += f"\n\n⚠️ المعلومات الناقصة: {missing}"
        for error in validation.errors:
            message += f"\n⚠️ {error}"
        can_save = False
    else:
        can_save = True
    message += "\n\nهل تريد حفظ الإعلان؟"
    markup = _add_preview_keyboard(can_save)
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=markup)
    else:
        await update.effective_message.reply_text(message, reply_markup=markup)
    return ADD_EDIT


async def _save_pending_profile(update: Any, context: Any) -> int:
    draft: ProfileDraft | None = context.user_data.get("pending_profile")
    if draft is None:
        await update.callback_query.edit_message_text("❌ ما في إعلان جاهز للحفظ.", reply_markup=_admin_main_keyboard())
        return END
    extraction = ProfileExtraction.model_validate({**draft.public_data, **draft.private_contact_data})
    validation = validate_profile_extraction(extraction, draft.private_contact_data)
    if not validation.ok:
        await update.callback_query.edit_message_text("⚠️ الإعلان ناقص وما فيني أحفظه قبل اكتماله.", reply_markup=_add_preview_keyboard(False))
        return ADD_EDIT
    preview_number = context.user_data.get("pending_request_number")
    try:
        with _session(context) as session:
            repo = ProfileRepository(session)
            if preview_number and repo.get(int(preview_number)) is not None:
                await update.callback_query.edit_message_text("⚠️ رقم الطلب تغيّر أثناء المراجعة. افتح معاينة جديدة قبل الحفظ.", reply_markup=_admin_main_keyboard())
                return END
            profile = repo.create(draft, request_number=int(preview_number) if preview_number else None)
            session.commit()
            number = profile.request_number
    except Exception:
        await update.callback_query.edit_message_text("❌ صار خطأ أثناء حفظ الإعلان. ما تم حفظه.", reply_markup=_admin_main_keyboard())
        return END
    context.user_data.clear()
    await update.callback_query.edit_message_text(f"✅ تم حفظ الإعلان بنجاح.\n\n📌 رقم الطلب: {number}", reply_markup=_admin_main_keyboard())
    return END


async def _show_latest(update: Any, context: Any) -> None:
    with _session(context) as session:
        rows = ProfileRepository(session).latest(20, include_inactive=True)
    if not rows:
        await update.callback_query.edit_message_text("📋 ما في عروض حالياً.", reply_markup=_admin_main_keyboard())
        return
    text = "📋 آخر الإعلانات:\n\n" + "\n".join(f"📌 طلب {row.request_number} — {row.name or 'بدون اسم'} — {row.age} سنة — {row.residence} — {row.status}" for row in rows)
    await update.callback_query.edit_message_text(text, reply_markup=_admin_main_keyboard())


async def _run_search(update: Any, context: Any, text: str) -> int:
    base = parse_search_text(text)
    filters = base
    ai: AIService = context.application.bot_data["ai_service"]
    ai_error = False
    if ai.is_configured:
        try:
            filters = merge_filters(base, filters_from_ai(await ai.parse_search_filters(text), text))
        except Exception:
            ai_error = True
    else:
        ai_error = True
    has_filters = any((filters.gender, filters.residence, filters.age_min, filters.age_max, filters.marital_status, filters.occupation, filters.education, filters.children_min is not None, filters.children_max is not None))
    if not has_filters:
        message = "⚠️ ما قدرت أفهم طلب البحث. جرّب مثلاً: بدي بنت من دمشق بين 22 و30 سنة عزباء."
        if ai_error:
            message += "\n\n⚠️ Gemini مو متاح حالياً لتحليل الطلب."
        await update.effective_message.reply_text(message, reply_markup=_back_to_admin_keyboard())
        return SEARCH_TEXT
    with _session(context) as session:
        rows = ProfileRepository(session).search(filters)
    if not rows:
        await update.effective_message.reply_text("🔎 ما لقينا نتائج مطابقة لهالمواصفات.", reply_markup=_back_to_admin_keyboard())
        return END
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = [[InlineKeyboardButton(f"📌 تفاصيل طلب {row.request_number}", callback_data=f"admin:profile:{row.request_number}")] for row in rows]
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")])
    await update.effective_message.reply_text(f"🔎 لقينا {len(rows)} نتيجة:\n\n" + "\n".join(f"📌 طلب {row.request_number} — {row.age} سنة — {row.residence} — {('🔒 محجوز' if row.status == 'reserved' else '✅ متاح')}" for row in rows), reply_markup=InlineKeyboardMarkup(buttons))
    return END


async def _show_admin_profile(update: Any, context: Any, request_number: int) -> None:
    with _session(context) as session:
        profile = ProfileRepository(session).get_with_contact(request_number)
    if profile is None:
        await update.callback_query.edit_message_text("❌ ما لقينا هالإعلان.", reply_markup=_admin_main_keyboard())
        return
    await update.callback_query.edit_message_text(format_admin_profile(profile), reply_markup=_profile_actions_keyboard(request_number, profile.get("status", "active")))


async def _begin_edit_from_message(update: Any, context: Any, request_number: int) -> int:
    with _session(context) as session:
        profile = ProfileRepository(session).get_with_contact(request_number)
    if profile is None:
        await update.effective_message.reply_text("❌ ما لقينا هالإعلان.", reply_markup=_back_to_admin_keyboard())
        return EDIT_REQUEST
    context.user_data["edit_request_number"] = request_number
    context.user_data["admin_flow"] = "edit_fields"
    await update.effective_message.reply_text(format_admin_profile(profile) + "\n\n✏️ ابعت التعديلات سطر بسطر.", reply_markup=_back_to_admin_keyboard())
    return EDIT_FIELDS


async def _begin_direct_edit(update: Any, context: Any, request_number: int | None) -> int:
    if request_number is None:
        return END
    with _session(context) as session:
        profile = ProfileRepository(session).get_with_contact(request_number)
    if profile is None:
        await update.callback_query.edit_message_text("❌ ما لقينا هالإعلان.", reply_markup=_admin_main_keyboard())
        return END
    context.user_data["edit_request_number"] = request_number
    context.user_data["admin_flow"] = "edit_fields"
    await update.callback_query.edit_message_text(format_admin_profile(profile) + "\n\n✏️ ابعت التعديلات سطر بسطر.", reply_markup=_back_to_admin_keyboard())
    return EDIT_FIELDS


async def _apply_direct_edit(update: Any, context: Any, text: str) -> int:
    request_number = context.user_data.get("edit_request_number")
    if not request_number:
        return END
    with _session(context) as session:
        repo = ProfileRepository(session)
        current = repo.get_with_contact(request_number)
        if current is None:
            await update.effective_message.reply_text("❌ ما لقينا هالإعلان.", reply_markup=_admin_main_keyboard())
            return END
        draft = extraction_to_draft(ProfileExtraction.model_validate(current))
        updated = apply_text_edits(draft, text)
        merged = ProfileExtraction.model_validate({**updated.public_data, **updated.private_contact_data})
        validation = validate_profile_extraction(merged, updated.private_contact_data)
        if not validation.ok:
            await update.effective_message.reply_text("⚠️ ما بقدر أحفظ التعديل قبل اكتمال البيانات الأساسية.", reply_markup=_back_to_admin_keyboard())
            return EDIT_FIELDS
        repo.update(request_number, {**updated.public_data, **updated.private_contact_data})
        session.commit()
        saved = repo.get_with_contact(request_number)
    context.user_data.clear()
    await update.effective_message.reply_text("✅ تم تعديل الإعلان.\n\n" + format_admin_profile(saved), reply_markup=_admin_main_keyboard())
    return END


async def _disable_profile(update: Any, context: Any, request_number: int | None) -> int:
    if request_number is None:
        return END
    with _session(context) as session:
        profile = ProfileRepository(session).disable(request_number)
        if profile is None:
            await update.callback_query.edit_message_text("❌ ما لقينا هالإعلان.", reply_markup=_admin_main_keyboard())
            return END
        session.commit()
    await update.callback_query.edit_message_text(f"✅ تم تعطيل الإعلان رقم {request_number}.", reply_markup=_admin_main_keyboard())
    return END


async def _show_stats(update: Any, context: Any) -> None:
    with _session(context) as session:
        stats = ProfileRepository(session).stats()
    text = ("📊 إحصائيات لقاء ونصيب\n\n" f"✅ متاحة: {stats['active']}\n" f"🔒 محجوزة: {stats['reserved']}\n" f"⛔ معطّلة: {stats['inactive']}\n" f"👩 إناث: {stats['female']}\n" f"👨 ذكور: {stats['male']}\n" f"💳 طلبات دفع معلّقة: {stats['pending_orders']}\n" f"✅ مدفوعة: {stats['paid_orders']}")
    await update.callback_query.edit_message_text(text, reply_markup=_admin_main_keyboard())


async def _send_backup(update: Any, context: Any) -> None:
    with _session(context) as session:
        data = json.dumps(export_all_data(session), ensure_ascii=False, indent=2).encode("utf-8")
    from telegram import BufferedInputFile
    await update.callback_query.message.reply_document(BufferedInputFile(data, filename="naseb-backup.json"), caption="💾 نسخة احتياطية من بيانات الإعلانات.")


async def _show_orders(update: Any, context: Any) -> None:
    with _session(context) as session:
        orders = OrderRepository(session).list_pending()
    if not orders:
        await update.callback_query.edit_message_text("💳 ما في طلبات معلّقة حالياً.", reply_markup=_admin_main_keyboard())
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton(f"🔎 {order.order_number}", callback_data=f"admin:order:view:{order.order_number}"), InlineKeyboardButton("✅", callback_data=f"admin:order:confirm:{order.order_number}"), InlineKeyboardButton("❌", callback_data=f"admin:order:reject:{order.order_number}")] for order in orders]
    rows.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:menu")])
    text = "💳 الطلبات المعلّقة:\n\n" + "\n".join(f"📌 طلب دفع {order.order_number} — الإعلان {order.profile.request_number} — {order.status}" for order in orders)
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def _view_order(update: Any, context: Any, order_number: int | None) -> int:
    if order_number is None:
        return END
    with _session(context) as session:
        order = OrderRepository(session).get(order_number)
        if order is None:
            await update.callback_query.edit_message_text("❌ ما لقينا طلب الدفع.", reply_markup=_admin_main_keyboard())
            return END
        profile = profile_to_dict(order.profile, order.profile.contact)
    text = (f"💳 طلب الدفع رقم {order.order_number}\n" f"👤 Telegram User ID: {order.user_telegram_id}\n" f"💵 المبلغ: {order.amount_usd} USD\n" f"💳 طريقة الدفع: {order.payment_method}\n" f"🧾 رقم العملية: {order.transaction_id or 'لم يُرسل بعد'}\n" f"📊 الحالة: {order.status}\n\n" + format_admin_profile(profile))
    await update.callback_query.edit_message_text(text, reply_markup=_order_actions_keyboard(order_number))
    return END


async def _confirm_order(update: Any, context: Any, order_number: int | None) -> int:
    if order_number is None:
        return END
    with _session(context) as session:
        order = OrderRepository(session).confirm_payment(order_number)
        if order is None:
            await update.callback_query.edit_message_text("❌ ما لقينا الطلب.", reply_markup=_admin_main_keyboard())
            return END
        session.commit()
        user_id = order.user_telegram_id
    try:
        await context.application.bot.send_message(user_id, f"✅ تم تأكيد دفعتك للطلب رقم {order_number}. الصفحة رح تتابع معك.")
    except Exception:
        pass
    await update.callback_query.edit_message_text(f"✅ تم تأكيد الدفع للطلب رقم {order_number}.", reply_markup=_admin_main_keyboard())
    return END


async def _reject_order(update: Any, context: Any, order_number: int | None) -> int:
    if order_number is None:
        return END
    with _session(context) as session:
        order = OrderRepository(session).reject_payment(order_number, "رفض يدوي من الأدمن")
        if order is None:
            await update.callback_query.edit_message_text("❌ ما لقينا الطلب.", reply_markup=_admin_main_keyboard())
            return END
        session.commit()
        user_id = order.user_telegram_id
    try:
        await context.application.bot.send_message(user_id, f"❌ تم رفض الدفع للطلب رقم {order_number}. إذا في مشكلة تواصل مع الصفحة.")
    except Exception:
        pass
    await update.callback_query.edit_message_text(f"❌ تم رفض الدفع للطلب رقم {order_number}.", reply_markup=_admin_main_keyboard())
    return END


def _number_suffix(data: str | None) -> int | None:
    if not data:
        return None
    try:
        return int(data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None
