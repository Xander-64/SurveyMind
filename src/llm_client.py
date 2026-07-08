"""Cloud LLM client using the OpenAI-compatible chat-completions format.

Provider, model and API key all come from environment variables (loaded from
the project's .env file — see .env.example):

    LLM_API_KEY   your API key. NEVER hardcode it or commit it to git.
    LLM_BASE_URL  API root, e.g. https://api.deepseek.com/v1
    LLM_MODEL     model name, e.g. deepseek-chat

Because DeepSeek, Kimi, Zhipu GLM and Anthropic's OpenAI-compatible layer all
speak this format, switching providers only means editing .env — no code
changes.
"""
from __future__ import annotations

import os

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


class LLMNotConfiguredError(RuntimeError):
    """Raised when ask_llm is called without an API key configured."""


def get_llm_config() -> dict[str, str]:
    return {
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "base_url": os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
        "model": os.getenv("LLM_MODEL", DEFAULT_MODEL).strip(),
    }


def is_llm_configured() -> bool:
    return bool(get_llm_config()["api_key"])


def ask_llm(prompt: str, timeout: float = 120.0) -> str:
    """Send one user prompt to the configured LLM and return the reply text."""
    config = get_llm_config()
    if not config["api_key"]:
        raise LLMNotConfiguredError(
            "LLM_API_KEY is not set. Copy .env.example to .env and fill in your key."
        )

    response = httpx.post(
        config["base_url"] + "/chat/completions",
        headers={"Authorization": "Bearer " + config["api_key"]},
        json={
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or [{}]
    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The LLM returned an empty response.")
    return content.strip()
