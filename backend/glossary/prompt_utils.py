MAX_GLOSSARY_PROMPT_TERMS = 30


def format_glossary_block(glossary: dict[str, str], *, limit: int = MAX_GLOSSARY_PROMPT_TERMS) -> str:
    if not glossary:
        return "（无术语表）"
    lines: list[str] = []
    for index, (source, target) in enumerate(glossary.items()):
        if index >= limit:
            break
        lines.append(f"- {source} → {target}")
    return "\n".join(lines)


def format_context_block(scenario: str, tone_hint: str = "") -> str:
    parts: list[str] = []
    if scenario.strip():
        parts.append(f"场景：{scenario.strip()}")
    if tone_hint.strip():
        parts.append(f"要求：{tone_hint.strip()}")
    return "\n".join(parts) if parts else "（未指定场景）"
