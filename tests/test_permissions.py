from app.services.permissions import is_admin, parse_admin_user_ids


def test_admin_id_is_recognized_from_configured_ids():
    assert is_admin(123, {123, 456}) is True


def test_non_admin_id_is_denied():
    assert is_admin(999, {123, 456}) is False


def test_admin_ids_parser_ignores_empty_and_invalid_values():
    assert parse_admin_user_ids("123, bad, 456, , 123") == {123, 456}
