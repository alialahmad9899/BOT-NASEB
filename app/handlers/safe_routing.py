"""Conversation-level routing adapters for fragile legacy/V2 paths."""

from __future__ import annotations

from typing import Any

from app.handlers.admin_entry import admin_callback, admin_text
from app.handlers.client import client_callback
from app.handlers.safe_order_views import (
    admin_order_view,
    admin_orders_view,
    client_order_view,
    client_orders_view,
)
from app.handlers.safe_search import admin_search_text


def _admin_order_list_requested(data: str) -> bool:
    return data == "admin:orders" or data.startswith("admin:v2:orders:")


def _admin_order_view_requested(data: str) -> bool:
    return data.startswith("admin:order:view:") or data.startswith("admin:v2:order:view:")


def _client_order_list_requested(data: str) -> bool:
    return data == "client:orders"


def _client_order_view_requested(data: str) -> bool:
    return data.startswith("client:order:view:")


def _admin_order_list_args(data: str) -> tuple[int, str]:
    if data == "admin:orders":
        return 0, "pending"
    parts = data.split(":")
    try:
        return max(0, int(parts[3])), parts[4] if len(parts) > 4 else "pending"
    except (ValueError, IndexError):
        return 0, "pending"


def _last_int(data: str) -> int | None:
    try:
        return int(data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None


async def admin_callback_router(update: Any, context: Any) -> int:
    data = update.callback_query.data or ""
    if _admin_order_list_requested(data):
        page, filter_name = _admin_order_list_args(data)
        return await admin_orders_view(update, context, page, filter_name)
    if _admin_order_view_requested(data):
        number = _last_int(data)
        if number is not None:
            return await admin_order_view(update, context, number)
    return await admin_callback(update, context)


async def admin_text_router(update: Any, context: Any) -> int:
    if context.user_data.get("v2_flow") == "search_input":
        return await admin_search_text(update, context)
    return await admin_text(update, context)


async def client_callback_router(update: Any, context: Any) -> int:
    data = update.callback_query.data or ""
    if _client_order_list_requested(data):
        return await client_orders_view(update, context)
    if _client_order_view_requested(data):
        number = _last_int(data)
        if number is not None:
            return await client_order_view(update, context, number)
    return await client_callback(update, context)
