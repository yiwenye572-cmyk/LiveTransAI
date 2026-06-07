import logging
import time
from dataclasses import dataclass

import httpx

from backend.config import DeepSeekConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


async def chat_completion(
    config: DeepSeekConfig,
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
    json_mode: bool = True,
) -> ChatCompletionResult:
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    payload: dict = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=config.timeout_sec) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    latency_ms = (time.perf_counter() - started) * 1000.0
    usage = data.get("usage") or {}
    return ChatCompletionResult(
        content=data["choices"][0]["message"]["content"],
        latency_ms=latency_ms,
        prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        total_tokens=int(usage.get("total_tokens", 0) or 0),
    )
