from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AstCorpus:
    hot_words: list[str] = field(default_factory=list)
    glossary: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.hot_words and not self.glossary
