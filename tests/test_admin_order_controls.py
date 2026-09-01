from app.keyboards.admin import (
    admin_orders_keyboard,
    confirm_delete_order_keyboard,
    confirm_delete_pending_orders_keyboard,
    order_actions_keyboard,
)


def callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_admin_order_actions_include_cancel_and_delete():
    data = callbacks(order_actions_keyboard(5001))
    assert "admin:order:reject:5001" in data
    assert "admin:order:delete:5001" in data
    assert "admin:orders" in data


def test_admin_pending_orders_list_includes_bulk_delete():
    data = callbacks(admin_orders_keyboard([5001, 5002], has_pending=True))
    assert "admin:order:delete:5001" in data
    assert "admin:order:delete:5002" in data
    assert "admin:orders:delete:pending" in data


def test_admin_delete_confirmations_have_cancel_path():
    data = callbacks(confirm_delete_order_keyboard(5001))
    assert "admin:order:delete:confirm:5001" in data
    assert "admin:orders" in data
    assert "admin:order:view:5001" in data

    data = callbacks(confirm_delete_pending_orders_keyboard())
    assert "admin:orders:delete:pending:confirm" in data
    assert "admin:orders" in data
