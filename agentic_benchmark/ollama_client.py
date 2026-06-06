from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any

from .code_processing import estimate_tokens, strip_ansi
from .models import AgentConfig, ModelCallResult

OLLAMA_API_URL = "http://localhost:11434/api/generate"
TIMEOUT_SECONDS = 600


def ns_to_s(value: Any) -> float:
    try:
        return float(value or 0) / 1_000_000_000
    except (TypeError, ValueError):
        return 0.0


def ollama(
    config: AgentConfig,
    prompt: str,
    *,
    api_url: str = OLLAMA_API_URL,
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> ModelCallResult:
    """Call local Ollama via HTTP API and preserve native token/timing metrics."""
    start = time.time()

    payload: dict[str, Any] = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.keep_alive,
        "options": {
            "num_ctx": config.num_ctx,
            "temperature": config.temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": config.num_predict,
        },
    }

    if config.json_mode:
        payload["format"] = "json"

    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama API call failed. Is Ollama running? URL={api_url}. Error: {exc}"
        ) from exc

    elapsed = time.time() - start

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {raw[:1000]}") from exc

    if "error" in data:
        raise RuntimeError(str(data["error"]))

    output = strip_ansi(str(data.get("response", "")).strip())

    return ModelCallResult(
        output=output,
        wallclock_s=elapsed,
        chars=len(output),
        words=len(output.split()),
        prompt_estimated_tokens=estimate_tokens(prompt),
        num_ctx=config.num_ctx,
        num_predict=config.num_predict,
        json_mode=config.json_mode,
        model=config.model,
        role=config.role,
        total_duration_s=ns_to_s(data.get("total_duration")),
        load_duration_s=ns_to_s(data.get("load_duration")),
        prompt_eval_count=int(data.get("prompt_eval_count") or 0),
        prompt_eval_duration_s=ns_to_s(data.get("prompt_eval_duration")),
        eval_count=int(data.get("eval_count") or 0),
        eval_duration_s=ns_to_s(data.get("eval_duration")),
    )


def run_agent(config: AgentConfig, prompt: str) -> ModelCallResult:
    """Run an agent role using its configuration."""
    return ollama(config, prompt)


def warm_agent(config: AgentConfig) -> ModelCallResult:
    """Warm a model outside measured benchmark rows for warm load-mode runs."""
    warm_config = replace(config, num_predict=1, json_mode=False)
    return ollama(warm_config, "Return OK.")


def unload_agent(config: AgentConfig) -> None:
    """Ask Ollama to unload a model so the next measured call captures load time."""
    unload_config = replace(config, keep_alive="0", num_predict=1, json_mode=False)
    ollama(unload_config, "")
