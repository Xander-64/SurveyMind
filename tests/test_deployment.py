"""Deployment configuration must remain public, configurable, and privacy-accurate."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_privacy_copy_and_config_order():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "问卷数据将临时存储于服务器，并在 1 小时内自动删除" in html
    assert "Survey data is stored temporarily on the server and automatically deleted within 1 hour" in html
    assert html.index('<script src="config.js"></script>') < html.index('<script src="data.js"></script>')


def test_frontend_api_url_is_configurable_with_local_default():
    config = (ROOT / "frontend" / "config.js").read_text(encoding="utf-8")
    data_js = (ROOT / "frontend" / "data.js").read_text(encoding="utf-8")
    assert 'apiBaseUrl: ""' in config
    assert "window.SURVEYMIND_CONFIG" in data_js
    assert "http://127.0.0.1:8000" in data_js


def test_render_config_never_declares_llm_key():
    render_config = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "CORS_ALLOWED_ORIGINS" in render_config
    assert "LLM_API_KEY" not in render_config
