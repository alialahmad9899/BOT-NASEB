from app.handlers.client import END, SEARCH_TEXT, next_search_state


def test_invalid_search_input_keeps_search_conversation_open():
    assert next_search_state(has_valid_filters=False) == SEARCH_TEXT


def test_completed_search_ends_search_conversation():
    assert next_search_state(has_valid_filters=True) == END
