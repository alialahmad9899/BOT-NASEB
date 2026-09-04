def test_save_handler_is_async():
    import inspect
    from app.handlers.incomplete_save_override import _save_add

    assert inspect.iscoroutinefunction(_save_add)
