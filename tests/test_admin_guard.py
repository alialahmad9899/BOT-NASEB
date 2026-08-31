from app.handlers.admin import admin_action_allowed


def test_admin_callback_policy_denies_non_admins():
    assert admin_action_allowed(999, {123}) is False
    assert admin_action_allowed(123, {123}) is True
