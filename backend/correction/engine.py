import json
import logging
import re

from backend.config import DeepSeekConfig
from backend.glossary.prompt_utils import format_context_block, format_glossary_block
from backend.llm.deepseek_client import chat_completion
from backend.memory.memory_store import MemoryStore
from backend.state.session_state import SessionState
from backend.summary.running_summary import RunningSummary

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是同声传译的校对专家。你会收到：
1. 【会话摘要】：本场演讲的主题、术语和要点
2. 【待校对段落】：最近若干句英文原文及中文快速翻译

请结合会话摘要理解指代、术语和上下文，但只修正【待校对段落】中的句子。
只修正确实有问题的句子，不要润色已经正确的翻译。修正应尽可能小，不要整句重写。

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

    async def run(
        self,
        window: list[dict],
        summary: RunningSummary,
        state: SessionState | None = None,
    ) -> list[dict]:
        if not self.config or not window:
            return []

        user_content = self._format_prompt(window, summary, state)
        system_prompt = self._build_system_prompt(state)
        try:
            raw = await chat_completion(
                self.config,
                system=system_prompt,
                user=user_content,
                temperature=0.2,
            )
        except Exception:
            logger.exception("DeepSeek correction API call failed")
            return []

        return self._parse_corrections(raw, window)

    def _build_system_prompt(self, state: SessionState | None) -> str:
        if state is None or not state.static_glossary:
            return SYSTEM_PROMPT

        lines = [
            SYSTEM_PROMPT,
            "",
            "【业务场景】",
            format_context_block(state.context_scenario, state.tone_hint),
            "以下术语译法必须保持一致：",
            format_glossary_block(state.static_glossary),
        ]
        return "\n".join(lines)

    def _format_prompt(
        self,
        window: list[dict],
        summary: RunningSummary,
        state: SessionState | None = None,
    ) -> str:
        focus_lines = []
        for item in window:
            focus_lines.append(
                f'{item["id"]} (v{item.get("version", 1)})\n'
                f'EN: {item.get("source", "")}\n'
                f'ZH: {item.get("translation", "")}'
            )

        blocks = [
            "【会话摘要】",
            summary.to_prompt_block(),
        ]
        if state is not None:
            memory_block = MemoryStore.recent_prompt_block(state, limit=5)
            if memory_block:
                blocks.extend(["", memory_block])

        blocks.extend(
            [
                "",
                "【待校对段落 - 仅可修改下列句子】",
                chr(10).join(focus_lines),
            ]
        )
        return "\n".join(blocks)

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
