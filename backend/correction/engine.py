import json
import logging
import re

import httpx

from backend.config import DeepSeekConfig

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是同声传译的校对专家。你会收到最近若干句英文原文及对应的中文快速翻译。

请基于上下文重新审视快速翻译。只修正确实有问题的句子，不要润色已经正确的翻译。
修正应尽可能小，不要整句重写。

以 JSON 输出，格式如下：
{
  "corrections": [
    {
      "sentence_id": "s_001",
      "base_version": 1,
      "new_version": 2,
      "old": "原快速翻译",
      "new": "修正后的翻译",
      "reason": "修正原因",
      "confidence": 0.92
    }
  ]
}

若无必要修正，返回 {"corrections": []}。只输出 JSON，不要 markdown。"""

CONFIDENCE_THRESHOLD = 0.85


class CorrectionEngine:
    """Async translation correction via DeepSeek official API."""

    def __init__(self, config: DeepSeekConfig | None) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config is not None

    async def run(self, window: list[dict]) -> list[dict]:
        if not self.config or not window:
            return []

        user_content = self._format_window(window)
        raw = await self._call_deepseek(user_content)
        if not raw:
            return []

        return self._parse_corrections(raw, window)

    def _format_window(self, window: list[dict]) -> str:
        lines = []
        for item in window:
            lines.append(
                f'{item["id"]} (v{item.get("version", 1)})\n'
                f'EN: {item.get("source", "")}\n'
                f'ZH: {item.get("translation", "")}'
            )
        return "\n\n".join(lines)

    async def _call_deepseek(self, user_content: str) -> str:
        assert self.config is not None
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_sec) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception:
            logger.exception("DeepSeek API call failed")
            return ""

    def _parse_corrections(self, raw: str, window: list[dict]) -> list[dict]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse correction JSON: %s", raw[:200])
            return []

        known_ids = {item["id"] for item in window}
        results: list[dict] = []

        for item in payload.get("corrections", []):
            confidence = float(item.get("confidence", 0))
            if confidence < CONFIDENCE_THRESHOLD:
                continue

            sentence_id = item.get("sentence_id", "")
            if sentence_id not in known_ids:
                continue

            old_text = item.get("old", "")
            new_text = item.get("new", "")
            if not new_text or old_text == new_text:
                continue

            results.append(
                {
                    "type": "correction",
                    "target_id": sentence_id,
                    "base_version": int(item.get("base_version", 1)),
                    "new_version": int(item.get("new_version", 2)),
                    "old_translation": old_text,
                    "new_translation": new_text,
                    "reason": item.get("reason", ""),
                    "confidence": confidence,
                }
            )

        return results
