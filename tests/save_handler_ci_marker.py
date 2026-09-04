def test_save_handler_ci_marker():
    from app.handlers.incomplete_save_override import _save_add
    assert callable(_save_add)
