from __future__ import annotations

MAX_HOT_WORDS = 20


def derive_hot_words(
    glossary: dict[str, str],
    llm_hot_words: list[str] | None = None,
    *,
    max_count: int = MAX_HOT_WORDS,
) -> list[str]:
    """Derive AST hot words from glossary keys and optional LLM suggestions."""
    if not glossary:
        return []

    glossary_keys = {key.casefold(): key for key in glossary}
    selected: list[str] = []
    seen: set[str] = set()

    for word in llm_hot_words or []:
        normalized = word.strip()
        if not normalized:
            continue
        canonical = glossary_keys.get(normalized.casefold())
        if canonical is None or canonical in seen:
            continue
        selected.append(canonical)
        seen.add(canonical)
        if len(selected) >= max_count:
            return selected

    if selected:
        return selected

    ranked = sorted(glossary.keys(), key=_hot_word_rank, reverse=True)
    for key in ranked:
        if len(key) <= 2:
            continue
        if key in seen:
            continue
        selected.append(key)
        seen.add(key)
        if len(selected) >= max_count:
            break

    return selected


def _hot_word_rank(word: str) -> tuple[int, int, str]:
    score = 0
    if " " in word or "-" in word:
        score += 3
    if len(word) >= 4:
        score += 2
    if word.isupper() and len(word) <= 6:
        score += 2
    return (score, len(word), word.casefold())
