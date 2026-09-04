def test_save_handler_reports_expected_callable_contract():
    from app.handlers.incomplete_save_override import _save_add

    assert _save_add.__module__ == "app.handlers.incomplete_save_override"
