import asyncio
from types import SimpleNamespace

from app.handlers import admin_entry


class ImmutableCallbackQuery:
    def __init__(self, data: str):
        object.__setattr__(self, "data", data)

    def __setattr__(self, key, value):
        if key == "data":
            raise AttributeError("Attribute `data` of class `CallbackQuery` can't be set!")
        object.__setattr__(self, key, value)



def test_force_save_routes_without_mutating_callback_query(monkeypatch):
    called = {"value": False}

    async def fake_save(update, context):
        called["value"] = True
        return admin_entry.END

    monkeypatch.setattr(admin_entry.admin_router.admin_v2, "_save_add", fake_save)
    monkeypatch.setattr(admin_entry, "_role", lambda context, user_id: "owner")

    query = ImmutableCallbackQuery("admin:v2:add:save:force")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={}),
    )

    result = asyncio.run(admin_entry.admin_callback(update, context))

    assert result == admin_entry.END
    assert called["value"] is True
    assert query.data == "admin:v2:add:save:force"
