from __future__ import annotations

import json
import logging
import re

from backend.config import DeepSeekConfig
from backend.glossary.glossary_bundle import GlossaryBundle
from backend.glossary.hot_words import MAX_HOT_WORDS, derive_hot_words
from backend.llm.deepseek_client import chat_completion
from backend.translator.languages import (
    source_language_label,
    target_language_label,
    validate_source_language,
)

logger = logging.getLogger(__name__)

MAX_TERMS = 30

_GLOSSARY_EXAMPLES: dict[str, tuple[str, str]] = {
    "en": ("federated learning", "联邦学习"),
    "ja": ("機械学習", "机器学习"),
    "pt": ("aprendizado de máquina", "机器学习"),
    "es": ("aprendizaje automático", "机器学习"),
    "id": ("pembelajaran mesin", "机器学习"),
    "de": ("maschinelles Lernen", "机器学习"),
    "fr": ("apprentissage automatique", "机器学习"),
}


def build_glossary_system_prompt(source_language: str) -> str:
    code = validate_source_language(source_language)
    source_label = source_language_label(code)
    target_label = target_language_label()
    example_source, example_target = _GLOSSARY_EXAMPLES.get(code, ("source term", "中文译法"))

    return f"""你是同声传译术语顾问。根据用户提供的业务场景和说明，生成{source_label}→{target_label}术语表。

要求：
1. 输出 15~25 条常见、实用的{source_label}→{target_label}术语（不要超过 30 条）
2. glossary_list 的 key 为{source_label}源词/短语，value 为推荐{target_label}译法
3. hot_words_list 从 glossary 的{source_label} key 中选取最容易听错的 10~20 个
4. tone_hint 用一句话概括翻译风格要求
5. 不要编造过于冷门、不会在演讲中出现的词

只输出 JSON，格式如下：
{{
  "tone_hint": "...",
  "glossary_list": {{ "{example_source}": "{example_target}" }},
  "hot_words_list": ["{example_source}"]
}}"""


class GlossaryError(RuntimeError):
    """Raised when glossary generation is unavailable or invalid."""


class GlossaryGenerator:
    def __init__(self, config: DeepSeekConfig | None) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config is not None

    async def generate(
        self,
        scenario: str,
        instruction: str,
        source_language: str | None = None,
    ) -> GlossaryBundle:
        if not self.config:
            raise GlossaryError("DeepSeek 未配置，无法生成术语表。请在 .env 中设置 DEEPSEEK_API_KEY。")

        scenario_text = scenario.strip()
        instruction_text = instruction.strip()
        if not scenario_text or not instruction_text:
            raise GlossaryError("业务场景和说明不能为空。")

        resolved_language = validate_source_language(source_language)
        user_content = (
            f"源语言：{source_language_label(resolved_language)}\n"
            f"目标语言：{target_language_label()}\n"
            f"业务场景：{scenario_text}\n"
            f"说明：{instruction_text}"
        )
        try:
            raw = await chat_completion(
                self.config,
                system=build_glossary_system_prompt(resolved_language),
                user=user_content,
                temperature=0.3,
            )
        except Exception as exc:
            logger.exception("Glossary generation API call failed")
            raise GlossaryError("术语表生成失败，请稍后重试。") from exc

        return parse_glossary_response(
            raw,
            scenario=scenario_text,
            instruction=instruction_text,
        )


def parse_glossary_response(
    raw: str,
    *,
    scenario: str,
    instruction: str,
) -> GlossaryBundle:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GlossaryError("术语表 JSON 解析失败。") from exc

    if not isinstance(payload, dict):
        raise GlossaryError("术语表响应格式无效。")

    glossary = GlossaryBundle._normalize_glossary(payload.get("glossary_list", {}))
    if len(glossary) > MAX_TERMS:
        glossary = dict(list(glossary.items())[:MAX_TERMS])

    if not glossary:
        raise GlossaryError("未生成有效术语，请调整场景描述后重试。")

    tone_hint = str(payload.get("tone_hint", "")).strip() or instruction
    raw_hot_words = GlossaryBundle._normalize_hot_words(payload.get("hot_words_list"))
    hot_words = derive_hot_words(glossary, raw_hot_words, max_count=MAX_HOT_WORDS)

    return GlossaryBundle(
        scenario=scenario,
        instruction=instruction,
        tone_hint=tone_hint,
        glossary_list=glossary,
        hot_words_list=hot_words,
    )
