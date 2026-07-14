from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE_PATH = PROJECT_ROOT / ".env"

LLM_CONFIG_KEYS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def _read_env_file(path: Path = ENV_FILE_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def get_llm_config() -> dict[str, str]:
    """Read LLM settings from environment variables, falling back to .env."""
    file_values = _read_env_file()
    return {key: os.environ.get(key) or file_values.get(key, "") for key in LLM_CONFIG_KEYS}


def is_llm_configured(config: dict[str, str] | None = None) -> bool:
    config = config or get_llm_config()
    return bool(config.get("LLM_API_KEY") and config.get("LLM_BASE_URL") and config.get("LLM_MODEL"))


def call_llm(
    system_prompt: str,
    user_prompt: str,
    config: dict[str, str] | None = None,
    temperature: float = 0.2,
    timeout: int = 90,
) -> str | None:
    """Call an OpenAI-compatible chat endpoint. Returns None on any failure."""
    config = config or get_llm_config()
    if not is_llm_configured(config):
        return None

    base_url = config["LLM_BASE_URL"].rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": config["LLM_MODEL"],
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['LLM_API_KEY']}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return content.strip() if isinstance(content, str) and content.strip() else None
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TypeError, ValueError, OSError):
        return None
