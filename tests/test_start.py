from app.handlers.start import reset_session_for_start, start_content_for_user


def test_start_returns_admin_menu_for_admin_user():
    result = start_content_for_user(123, {123})

    assert result.role == "admin"
    assert "لوحة الأدمن" in result.text
    assert "اختار القسم اللي بدك تديره" in result.text


def test_start_returns_client_menu_for_regular_user():
    result = start_content_for_user(999, {123})

    assert result.role == "client"
    assert "لقاء ونصيب" in result.text
    assert "💗 بدي عروس" in result.text
    assert "🤵 بدي عريس" in result.text
    assert "🔎 بدي أبحث بنفسي" in result.text
    assert "📋 شوف العروض" in result.text
    assert "💳 طلباتي" in result.text
    assert "ℹ️ كيف بتشتغل الصفحة؟" in result.text
    assert "لوحة الأدمن" not in result.text


def test_start_session_reset_clears_previous_flow_state():
    context = type("Context", (), {})()
    context.user_data = {
        "client_flow": "search",
        "search_target_gender": "female",
        "pending_profile": "stale",
    }

    reset_session_for_start(context)

    assert context.user_data == {}
