import time

from backend.memory.memory_entry import MemoryEntry
from backend.state.session_state import SessionState
from backend.translator.languages import source_language_tag, target_language_tag


class MemoryStore:
    """Structured correction memory for downstream LLM prompts."""

    def append_batch(
        self,
        window: list[dict],
        applied_corrections: list[dict],
        state: SessionState,
    ) -> None:
        if not applied_corrections:
            return

        sentence_map = {item["id"]: item for item in state.displayed_sentences}
        correction_map = {item["target_id"]: item for item in applied_corrections}

        for sentence_id, correction in correction_map.items():
            if sentence_id not in {item["id"] for item in window}:
                continue

            current = sentence_map.get(sentence_id)
            if current is None:
                continue

            hints = self._build_hints(correction)
            entry = MemoryEntry(
                sentence_id=sentence_id,
                source=current.get("source", ""),
                translation=current.get("translation", ""),
                version=int(current.get("version", 1)),
                correction_hints=hints,
                recorded_at=time.time(),
            )
            self._upsert_entry(state, entry)

    @staticmethod
    def _upsert_entry(state: SessionState, entry: MemoryEntry) -> None:
        for index, existing in enumerate(state.memory_entries):
            if existing.sentence_id == entry.sentence_id:
                state.memory_entries[index] = entry
                return
        state.memory_entries.append(entry)

    @staticmethod
    def _build_hints(correction: dict) -> list[str]:
        hints: list[str] = []
        reason = str(correction.get("reason", "")).strip()
        if reason:
            hints.append(f"reason: {reason}")

        old_text = str(correction.get("old_translation", "")).strip()
        new_text = str(correction.get("new_translation", "")).strip()
        if old_text and new_text and old_text != new_text:
            hints.append(f"term: {old_text}→{new_text}")

        return hints

    @staticmethod
    def recent_prompt_block(state: SessionState, limit: int = 5) -> str:
        if not state.memory_entries:
            return ""

        lines = ["【近期纠错记忆】"]
        source_tag = source_language_tag(state.source_language)
        target_tag = target_language_tag()
        for entry in state.memory_entries[-limit:]:
            hints = "；".join(entry.correction_hints) if entry.correction_hints else "—"
            lines.append(
                f'{entry.sentence_id} {source_tag}: {entry.source}\n'
                f'{target_tag}: {entry.translation}\nhints: {hints}'
            )
        return "\n\n".join(lines)
