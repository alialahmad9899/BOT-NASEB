from app.services.runtime import DatabaseNotConfiguredError, user_message_for_error


def test_database_not_configured_error_has_user_facing_message():
    message = user_message_for_error(DatabaseNotConfiguredError())
    assert "قاعدة البيانات" in message
    assert "غير مهيأة" in message


def test_unexpected_error_gets_safe_generic_message():
    message = user_message_for_error(RuntimeError("secret internal detail"))
    assert "secret internal detail" not in message
    assert "خطأ غير متوقع" in message
