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
    return data == "admin:orders" or data == "admin:v2:orders:0:pending" or data.startswith("admin:v2:orders:")


def _admin_order_view_requested(data: str) -> bool:
    return data.startswith("admin:order:view:") or data.startswith("admin:v2:order:view:")


def _client_order_list_requested(data: str) -> bool:
    return data == "client:orders"


def _client_order_view_requested(data: str) -> bool:
    return data.startswith("client:order:view:")


async def admin_callback_router(update: Any, context: Any) -> int:
    data = update.callback_query.data or ""
    if _admin_order_list_requested(data):
        return await admin_orders_view(update, context)
    if _admin_order_view_requested(data):
        return await admin_order_view(update, context)
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
        return await client_order_view(update, context)
    return await client_callback(update, context)
