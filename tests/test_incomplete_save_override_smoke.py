def test_hardened_save_module_imports_cleanly():
    from app.handlers.incomplete_save_override import install

    assert callable(install)
