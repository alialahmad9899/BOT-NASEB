import asyncio
from types import SimpleNamespace

from app.handlers import safe_routing


class ImmutableCallbackQuery:
    def __init__(self, data: str):
        object.__setattr__(self, "data", data)

    def __setattr__(self, key, value):
        if key == "data":
            raise AttributeError("Attribute `data` of class `CallbackQuery` can't be set!")
        object.__setattr__(self, key, value)


def test_force_save_is_routed_directly_without_callback_mutation(monkeypatch):
    called = {"value": False}

    async def fake_save(update, context):
        called["value"] = True
        return 123

    async def legacy_route_must_not_run(update, context):
        raise AssertionError("force-save must not reach admin_entry.admin_callback")

    monkeypatch.setattr(safe_routing.admin_v2, "_save_add", fake_save)
    monkeypatch.setattr(safe_routing, "admin_callback", legacy_route_must_not_run)

    query = ImmutableCallbackQuery("admin:v2:add:save:force")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    result = asyncio.run(safe_routing.admin_callback_router(update, context))

    assert result == 123
    assert called["value"] is True
    assert query.data == "admin:v2:add:save:force"
