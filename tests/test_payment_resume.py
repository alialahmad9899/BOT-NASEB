from app.database.models import Order
from app.keyboards.client import client_payment_keyboard, client_order_detail_keyboard


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_client_payment_ui_does_not_request_transaction_number():
    callbacks = _callbacks(client_payment_keyboard())
    assert not any(callback.startswith("client:payment:submit") for callback in callbacks)
    assert "client:orders" in callbacks
    assert "client:menu" in callbacks


def test_order_model_has_whatsapp_contact_field():
    assert hasattr(Order, "whatsapp")


def test_order_detail_does_not_offer_transaction_entry():
    callbacks = _callbacks(client_order_detail_keyboard("pending_payment", 5001))
    assert not any(callback.startswith("client:payment:submit") for callback in callbacks)
