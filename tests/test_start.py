from app.handlers.start import start_content_for_user


def test_start_returns_admin_menu_for_admin_user():
    result = start_content_for_user(123, {123})

    assert result.role == "admin"
    assert "لوحة الأدمن" in result.text
    assert "➕ إضافة إعلان" in result.text


def test_start_returns_client_menu_for_regular_user():
    result = start_content_for_user(999, {123})

    assert result.role == "client"
    assert "لقاء ونصيب" in result.text
    assert "📋 تصفح العروض" in result.text
    assert "لوحة الأدمن" not in result.text
