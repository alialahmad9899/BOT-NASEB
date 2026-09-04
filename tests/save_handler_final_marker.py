def test_save_handler_final_marker():
    from app.handlers.incomplete_save_override import _save_add
    assert _save_add is not None
