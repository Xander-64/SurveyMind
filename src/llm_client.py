from __future__ import annotations

import os


def ask_local_llm(prompt: str, model: str = "qwen3:4b") -> str:
    """Call a local Ollama model and return the generated text."""
    try:
        import ollama
    except ImportError:
        return "未安装 ollama Python 依赖，请先执行 `pip install ollama`。"

    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    try:
        client = ollama.Client(host=host)
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
    except Exception as exc:
        raw_error = getattr(exc, "error", str(exc))
        error_message = str(raw_error)
        lowered_message = error_message.lower()
        status_code = getattr(exc, "status_code", None)

        connection_keywords = (
            "failed to connect",
            "connection refused",
            "timed out",
            "operation not permitted",
            "connection aborted",
            "connection reset",
            "cannot assign requested address",
        )
        if status_code is None and any(keyword in lowered_message for keyword in connection_keywords):
            return (
                "无法连接到本地 Ollama 服务。"
                f"当前地址：`{host}`。"
                "请先运行 `ollama serve`，或确认 Ollama 桌面应用正在运行后再重试。"
            )

        model_not_found_keywords = (
            "model not found",
            "pull model manifest",
            "file does not exist",
            "not found, try pulling it first",
        )
        if status_code == 404 or any(keyword in lowered_message for keyword in model_not_found_keywords):
            return f"本地模型 `{model}` 不存在或尚未下载。请先运行 `ollama pull {model}`。"

        return f"调用本地 Ollama 模型失败：{error_message}"

    content = ""
    if hasattr(response, "message") and hasattr(response.message, "content"):
        content = str(response.message.content or "").strip()
    elif isinstance(response, dict):
        content = str(response.get("message", {}).get("content", "")).strip()

    if not content:
        return "本地模型已返回响应，但内容为空。请确认模型可正常生成文本。"
    return content
