import json
import logging
import re

from backend.config import DeepSeekConfig
from backend.glossary.prompt_utils import format_context_block, format_glossary_block
from backend.llm.deepseek_client import ChatCompletionResult, chat_completion
from backend.utils.session_metrics import SessionMetrics
from backend.state.session_state import SessionState
from backend.summary.running_summary import RunningSummary
from backend.translator.languages import (
    source_language_label,
    source_language_tag,
    target_language_label,
    target_language_tag,
)

logger = logging.getLogger(__name__)


def build_summary_system_prompt(source_label: str, target_label: str) -> str:
    return f"""你是同声传译会话的记录员。根据【旧摘要】和【新增句子】，输出更新后的会话摘要 JSON。

要求：
1. 保留仍相关的 topic、术语、要点，合并重复信息，删除过时细节
2. bullet_points 最多 8 条，每条不超过 40 字
3. term_map 只保留本场已出现术语，格式为 {{"{source_label}源词": "推荐{target_label}译法"}}
4. 不要编造未出现的信息

输出 JSON 格式：
{{
  "topic": "演讲主题",
  "term_map": {{"federated learning": "联邦学习"}},
  "bullet_points": ["要点1", "要点2"]
}}

只输出 JSON，不要 markdown。"""


class SummaryUpdater:
    """Incremental LLM summary over the current translation session."""

    def __init__(self, config: DeepSeekConfig | None) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config is not None

    async def update(self, state: SessionState) -> bool:
        if not self.config:
            return False

        start_index = state.running_summary.last_summarized_at
        new_sentences = state.displayed_sentences[start_index:]
        if not new_sentences:
            return False

        user_content = self._format_input(state)
        system_prompt = self._build_system_prompt(state)
        try:
            result = await chat_completion(
                self.config,
                system=system_prompt,
                user=user_content,
                temperature=0.1,
            )
        except Exception:
            logger.exception("Summary update API call failed")
            state.metrics.record_llm_call("summary", latency_ms=0, ok=False)
            return False

        self._record_llm_call(state.metrics, result)
        payload = self._parse_json(result.content)
        if payload is None:
            return False

        state.running_summary.apply_payload(payload, sentence_count=state.sentence_count)
        logger.info(
            "Summary updated at sentence %s with %s new sentences",
            state.sentence_count,
            len(new_sentences),
        )
        return True

    @staticmethod
    def _record_llm_call(metrics: SessionMetrics, result: ChatCompletionResult) -> None:
        metrics.record_llm_call(
            "summary",
            latency_ms=result.latency_ms,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            ok=True,
        )

    def _build_system_prompt(self, state: SessionState) -> str:
        source_label = source_language_label(state.source_language)
        target_label = target_language_label()
        return build_summary_system_prompt(source_label, target_label)

    def _format_input(self, state: SessionState) -> str:
        summary = state.running_summary
        start_index = summary.last_summarized_at
        new_sentences = state.displayed_sentences[start_index:]
        source_tag = source_language_tag(state.source_language)
        target_tag = target_language_tag()
        old_summary = {
            "topic": summary.topic,
            "term_map": summary.term_map,
            "bullet_points": summary.bullet_points,
        }
        blocks = [
            format_context_block(state.context_scenario, state.tone_hint),
            "",
            "【静态术语表】",
            format_glossary_block(state.static_glossary),
            "",
            "【旧摘要】",
            json.dumps(old_summary, ensure_ascii=False),
            "",
            "【新增句子】",
        ]
        for item in new_sentences:
            blocks.append(
                f'{item["id"]}\n{source_tag}: {item.get("source", "")}\n'
                f'{target_tag}: {item.get("translation", "")}'
            )
        return "\n\n".join(blocks)

    def _parse_json(self, raw: str) -> dict | None:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse summary JSON: %s", raw[:200])
            return None
