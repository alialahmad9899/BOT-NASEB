from app.keyboards.client import client_order_detail_keyboard


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_pending_order_shows_transaction_input_button_with_order_number():
    callbacks = _callbacks(client_order_detail_keyboard("pending_payment", 5001))
    assert "client:payment:submit:5001" in callbacks


def test_reviewed_order_does_not_offer_duplicate_transaction_input():
    callbacks = _callbacks(client_order_detail_keyboard("pending_review", 5001))
    assert "client:payment:submit:5001" not in callbacks
