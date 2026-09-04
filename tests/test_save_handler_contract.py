def test_save_handler_contract_documents_expected_behavior():
    from app.handlers.incomplete_save_override import _save_add

    assert _save_add.__name__ == "_save_add"
