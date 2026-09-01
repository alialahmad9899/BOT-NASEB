from pathlib import Path


def test_render_uses_one_web_service_and_no_render_postgres():
    text = Path("render.yaml").read_text(encoding="utf-8")
    assert "type: web" in text
    assert "type: postgres" not in text
    assert text.count("key: DATABASE_URL") == 1


def test_render_and_env_example_use_current_gemini_model():
    render_text = Path("render.yaml").read_text(encoding="utf-8")
    env_text = Path(".env.example").read_text(encoding="utf-8")
    assert "value: gemini-3.5-flash-lite" in render_text
    assert "AI_MODEL=gemini-3.5-flash-lite" in env_text
