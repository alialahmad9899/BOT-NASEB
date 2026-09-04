def test_install_replaces_admin_v2_save_handler():
    from app.handlers import admin_v2
    from app.handlers.incomplete_save_override import _save_add, install

    original = admin_v2._save_add
    try:
        install()
        assert admin_v2._save_add is _save_add
    finally:
        admin_v2._save_add = original
