"""Safe order list/detail handlers that never use detached ORM relations."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import desc, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.database.admin_models import OrderAdminMeta
from app.database.models import Order
from app.database.repositories import OrderRepository, ProfileRepository
from app.keyboards.client import client_main_keyboard, client_order_detail_keyboard, client_orders_keyboard
from app.services.admin_meta import get_order_meta
from app.services.profiles import format_admin_profile
from app.handlers import admin_v2

END = ConversationHandler.END


def _session(context: Any):
    factory = context.application.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError("قاعدة البيانات غير مهيأة")
    return factory()


def _payment_label(status: str | None) -> str:
    return {
        "pending_payment": "🟠 بانتظار الدفع",
        "pending_review": "🟠 قيد المتابعة",
        "paid": "✅ مدفوع",
        "rejected": "❌ مرفوض",
    }.get(status or "", "🟠 قيد المتابعة")


def _contact_label(status: str | None) -> str:
    return {
        "new": "🆕 جديد",
        "contacted": "📞 تم التواصل",
        "opened": "🤝 مفتوح",
        "completed": "✅ مكتمل",
        "cancelled": "❌ ملغى",
    }.get(status or "", "🆕 جديد")


def load_admin_order_rows(session, page: int, filter_name: str, limit: int = 10) -> tuple[list[dict[str, Any]], bool]:
    """Load all data needed by the admin list while the session is still open."""
    stmt = (
        select(Order, OrderAdminMeta)
        .outerjoin(OrderAdminMeta, OrderAdminMeta.order_id == Order.id)
        .order_by(desc(Order.created_at))
        .offset(max(0, page) * limit)
        .limit(limit + 1)
    )
    if filter_name == "pending":
        stmt = stmt.where(Order.status.in_(["pending_payment", "pending_review"]))
    elif filter_name == "paid":
        stmt = stmt.where(Order.status == "paid")
    elif filter_name == "completed":
        stmt = stmt.where(OrderAdminMeta.contact_status == "completed")

    db_rows = list(session.execute(stmt).all())
    has_next = len(db_rows) > limit
    db_rows = db_rows[:limit]
    rows: list[dict[str, Any]] = []
    for order, meta in db_rows:
        meta = meta or get_order_meta(session, int(order.id), create=True)
        profile_request = order.profile.request_number if order.profile else None
        rows.append({
            "order_number": int(order.order_number),
            "profile_request_number": profile_request,
            "status": order.status,
            "payment_status": meta.payment_status if meta else "pending",
            "contact_status": meta.contact_status if meta else "new",
            "whatsapp": order.whatsapp,
            "amount_usd": str(order.amount_usd),
        })
    session.commit()
    return rows, has_next


def load_client_order_rows(session, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    orders = list(
        session.scalars(
            select(Order)
            .where(Order.user_telegram_id == user_id)
            .order_by(desc(Order.created_at))
            .limit(max(1, min(limit, 50)))
        ).all()
    return [
        {
            "order_number": int(order.order_number),
            "profile_request_number": order.profile.request_number if order.profile else None,
            "status": order.status,
            "whatsapp": order.whatsapp,
        }
        for order in orders
    ]


def load_admin_order_detail(session, number: int) -> dict[str, Any] | None:
    order = OrderRepository(session).get(number)
    if order is None:
        return None
    meta = get_order_meta(session, int(order.id), create=True)
    profile_request = order.profile.request_number if order.profile else None
    profile = ProfileRepository(session).get_with_contact(profile_request) if profile_request is not None else None
    data = {
        "order_number": int(order.order_number),
        "profile_request_number": profile_request,
        "user_telegram_id": int(order.user_telegram_id),
        "whatsapp": order.whatsapp,
        "amount_usd": str(order.amount_usd),
        "payment_method": order.payment_method,
        "payment_status": meta.payment_status if meta else "pending",
        "contact_status": meta.contact_status if meta else "new",
        "profile": profile,
    }
    session.commit()
    return data


def load_client_order_detail(session, number: int, user_id: int) -> dict[str, Any] | None:
    order = OrderRepository(session).get(number)
    if order is None or int(order.user_telegram_id) != int(user_id):
        return None
    data = {
        "order_number": int(order.order_number),
        "profile_request_number": order.profile.request_number if order.profile else None,
        "amount_usd": str(order.amount_usd),
        "payment_method": order.payment_method,
        "whatsapp": order.whatsapp,
        "status": order.status,
    }
    return data


def _admin_order_keyboard(row: dict[str, Any]) -> InlineKeyboardMarkup:
    order_number = row["order_number"]
    buttons = [[InlineKeyboardButton(f"🔎 {order_number}", callback_data=f"admin:v2:order:view:{order_number}")]]
    if row["payment_status"] == "pending":
        buttons.append([
            InlineKeyboardButton("✅", callback_data=f"admin:v2:order:confirm:{order_number}"),
            InlineKeyboardButton("❌", callback_data=f"admin:v2:order:reject:{order_number}"),
        ])
    return InlineKeyboardMarkup(buttons)


def _admin_order_detail_keyboard(data: dict[str, Any]) -> InlineKeyboardMarkup:
    number = data["order_number"]
    rows: list[list[InlineKeyboardButton]] = []
    if data["payment_status"] == "pending":
        rows.append([
            InlineKeyboardButton("💰 تأكيد الدفع", callback_data=f"admin:v2:order:confirm:{number}"),
            InlineKeyboardButton("❌ رفض الدفع", callback_data=f"admin:v2:order:reject:{number}"),
        ])
    contact = data["contact_status"]
    if contact == "new":
        rows.append([InlineKeyboardButton("📞 تم التواصل", callback_data=f"admin:v2:order:contacted:{number}")])
    elif contact == "contacted":
        rows.append([InlineKeyboardButton("🤝 فتح التواصل", callback_data=f"admin:v2:order:opened:{number}")])
    elif contact == "opened":
        rows.append([InlineKeyboardButton("✅ إغلاق الطلب", callback_data=f"admin:v2:order:complete:{number}")])
    if data.get("whatsapp"):
        digits = re.sub(r"\D", "", str(data["whatsapp"]))
        if digits.startswith("0"):
            digits = "963" + digits[1:]
        rows.append([InlineKeyboardButton("📱 فتح واتساب", url=f"https://wa.me/{digits}")])
    rows.extend([
        [InlineKeyboardButton("🗑️ حذف الطلب", callback_data=f"admin:v2:order:delete:{number}")],
        [InlineKeyboardButton("⬅️ طلبات التواصل", callback_data="admin:v2:orders:0:pending")],
        [InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")],
    ])
    return InlineKeyboardMarkup(rows)


async def admin_orders_view(update: Any, context: Any, page: int, filter_name: str) -> int:
    with _session(context) as session:
        rows, has_next = load_admin_order_rows(session, page, filter_name)
    if not rows:
        await update.callback_query.edit_message_text("💳 ما في طلبات بهالقسم.", reply_markup=admin_v2._dashboard_keyboard())
        return END
    text = "💳 طلبات التواصل\n\n" + "\n".join(
        f"📌 طلب {row['order_number']} — إعلان {row['profile_request_number'] or '?'}\n"
        f"{_payment_label(row['status'])} — {_contact_label(row['contact_status'])}\n"
        f"📱 {row['whatsapp'] or 'بدون واتساب'}"
        for row in rows
    )
    buttons: list[list[InlineKeyboardButton]] = []
    for row in rows:
        buttons.extend(_admin_order_keyboard(row).inline_keyboard)
    buttons.append([
        InlineKeyboardButton("🟢 المدفوعة", callback_data="admin:v2:orders:0:paid"),
        InlineKeyboardButton("✅ المكتملة", callback_data="admin:v2:orders:0:completed"),
    ])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin:v2:orders:{page-1}:{filter_name}"))
    if has_next:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin:v2:orders:{page+1}:{filter_name}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ لوحة الأدمن", callback_data="admin:v2:dashboard")])
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return END


async def admin_order_view(update: Any, context: Any, number: int) -> int:
    with _session(context) as session:
        data = load_admin_order_detail(session, number)
    if data is None:
        await update.callback_query.edit_message_text("❌ ما لقينا طلب التواصل.", reply_markup=admin_v2._dashboard_keyboard())
        return END
    profile_text = format_admin_profile(data["profile"]) if data.get("profile") else "❌ بيانات الإعلان غير موجودة"
    text = (
        f"💳 طلب التواصل رقم {data['order_number']}\n\n"
        f"🧾 الإعلان: {data['profile_request_number'] or '—'}\n"
        f"🆔 Telegram ID: {data['user_telegram_id']}\n"
        f"📱 WhatsApp: {data['whatsapp'] or '—'}\n"
        f"💵 المبلغ: {data['amount_usd']} USD\n"
        f"💳 طريقة الدفع: {data['payment_method']}\n"
        f"💳 حالة الدفع: {data['payment_status']}\n"
        f"🤝 حالة التواصل: {data['contact_status']}\n\n"
        + profile_text
    )
    await update.callback_query.edit_message_text(text, reply_markup=_admin_order_detail_keyboard(data))
    return END


async def client_orders_view(update: Any, context: Any) -> int:
    user_id = int(update.effective_user.id)
    context.user_data.clear()
    with _session(context) as session:
        rows = load_client_order_rows(session, user_id)
    if not rows:
        await update.callback_query.edit_message_text("💳 ما عندك طلبات تواصل حالياً.", reply_markup=client_main_keyboard())
        return END
    blocks = []
    numbers = []
    for row in rows:
        numbers.append(row["order_number"])
        blocks.append(
            f"📌 طلب {row['order_number']}\n"
            f"💍 الإعلان: {row['profile_request_number'] or '—'}\n"
            f"{_payment_label(row['status'])}\n"
            f"📱 واتساب: {row['whatsapp'] or 'غير مسجل'}"
        )
    await update.callback_query.edit_message_text("💳 طلباتي\n\n" + "\n\n".join(blocks), reply_markup=client_orders_keyboard(numbers))
    return END


async def client_order_view(update: Any, context: Any, number: int) -> int:
    with _session(context) as session:
        data = load_client_order_detail(session, number, int(update.effective_user.id))
    if data is None:
        await update.callback_query.edit_message_text("❌ ما لقينا هالطلب ضمن طلباتك.", reply_markup=client_main_keyboard())
        return END
    text = "\n".join([
        "📩 تفاصيل طلب التواصل",
        "",
        f"📌 رقم الطلب: {data['order_number']}",
        f"💍 الإعلان: {data['profile_request_number'] or '—'}",
        f"💵 قيمة الخدمة: {data['amount_usd']} دولار",
        f"💳 طريقة الدفع: {data['payment_method']}",
        f"📱 واتساب: {data['whatsapp'] or 'غير مسجل'}",
        _payment_label(data['status']),
    ])
    await update.callback_query.edit_message_text(text, reply_markup=client_order_detail_keyboard(data['status'], data['order_number']))
    return END
