from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GlossaryBundle:
    scenario: str
    instruction: str
    tone_hint: str
    glossary_list: dict[str, str] = field(default_factory=dict)
    hot_words_list: list[str] = field(default_factory=list)

    def to_api_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "instruction": self.instruction,
            "tone_hint": self.tone_hint,
            "term_map": dict(self.glossary_list),
            "term_count": len(self.glossary_list),
            "hot_words_list": list(self.hot_words_list),
        }

    @classmethod
    def from_client_payload(cls, payload: dict | None) -> GlossaryBundle | None:
        if not payload:
            return None

        glossary = cls._normalize_glossary(payload.get("term_map") or payload.get("glossary_list"))
        if not glossary and not str(payload.get("scenario", "")).strip():
            return None

        scenario = str(payload.get("scenario", "")).strip()
        instruction = str(payload.get("instruction", "")).strip()
        tone_hint = str(payload.get("tone_hint", "")).strip() or instruction
        hot_words = cls._normalize_hot_words(payload.get("hot_words_list"))
        if not hot_words:
            hot_words = list(glossary.keys())[:20]

        return cls(
            scenario=scenario,
            instruction=instruction,
            tone_hint=tone_hint,
            glossary_list=glossary,
            hot_words_list=hot_words,
        )

    @staticmethod
    def _normalize_glossary(raw: object) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        return {
            str(key).strip(): str(value).strip()
            for key, value in raw.items()
            if str(key).strip() and str(value).strip()
        }

    @staticmethod
    def _normalize_hot_words(raw: object) -> list[str]:
        if not isinstance(raw, list):
            return []
        words: list[str] = []
        for item in raw:
            word = str(item).strip()
            if word:
                words.append(word)
        return words
