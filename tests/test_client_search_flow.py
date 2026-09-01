from app.handlers.client import END, SEARCH_CONFIRM, SEARCH_TEXT, next_search_state


def test_invalid_search_input_keeps_search_conversation_open():
    assert next_search_state(has_valid_filters=False) == SEARCH_TEXT


def test_completed_search_enters_confirmation_step():
    assert next_search_state(has_valid_filters=True) == SEARCH_CONFIRM
