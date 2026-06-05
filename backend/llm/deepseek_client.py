import logging

import httpx

from backend.config import DeepSeekConfig

logger = logging.getLogger(__name__)


async def chat_completion(
    config: DeepSeekConfig,
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
    json_mode: bool = True,
) -> str:
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

    async with httpx.AsyncClient(timeout=config.timeout_sec) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
