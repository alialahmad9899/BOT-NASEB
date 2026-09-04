import asyncio
from types import SimpleNamespace

from app.handlers import admin_router


def test_incomplete_save_callback_routes_directly_to_save_handler(monkeypatch):
    calls = []

    async def fake_save(update, context):
        calls.append((update, context))
        return 987

    monkeypatch.setattr(admin_router.admin_v2, "_save_add", fake_save)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="admin:v2:add:save"))
    context = SimpleNamespace()

    result = asyncio.run(admin_router.admin_callback(update, context))

    assert result == 987
    assert calls == [(update, context)]
