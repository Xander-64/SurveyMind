"""Unit tests for the cloud LLM client — no network, no real quota."""
from __future__ import annotations

import pytest

from src import llm_client
from src.llm_client import LLMNotConfiguredError, ask_llm, get_llm_config, is_llm_configured


def test_not_configured_raises(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert is_llm_configured() is False
    with pytest.raises(LLMNotConfiguredError):
        ask_llm("hello")


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k-123")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1/")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    config = get_llm_config()
    assert config["api_key"] == "k-123"
    assert config["base_url"] == "https://example.com/v1"  # trailing slash stripped
    assert config["model"] == "test-model"
    assert is_llm_configured() is True


def test_ask_llm_parses_openai_compatible_response(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k-123")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "  你好，这是报告。  "}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    result = ask_llm("测试提示词")

    assert result == "你好，这是报告。"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer k-123"
    assert captured["json"]["messages"][0]["content"] == "测试提示词"


def test_ask_llm_empty_response_raises(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k-123")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": ""}}]}

    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: FakeResponse())
    with pytest.raises(RuntimeError):
        ask_llm("hi")
