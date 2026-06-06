import re

from backend.format.formatted_document import FormatSlot, FormattedDocument
from backend.state.session_state import SessionState

PUNCT_ENDINGS = ("。", "！", "？", "…")
WEAK_TRAILING = "，、；： "
NUMBER_REPLACEMENTS = (
    (re.compile(r"\b100\s+million\b", re.I), "1亿"),
    (re.compile(r"\b1\s+billion\b", re.I), "10亿"),
)

PARAGRAPH_GAP_MS = 2000
MAX_SENTENCES_PER_PARAGRAPH = 4


class TextFormatter:
    """Rule-based Chinese translation normalization and paragraph assembly."""

    def __init__(self) -> None:
        self._paragraph_seq = 0

    def flush_window(self, window: list[dict], state: SessionState) -> list[dict]:
        deltas: list[dict] = []
        sentence_map = {item["id"]: item for item in state.displayed_sentences}
        for item in window:
            sentence_id = item["id"]
            if state.formatted_doc.has_sentence(sentence_id):
                continue
            current = sentence_map.get(sentence_id)
            if current is None:
                continue
            delta = self._append_sentence(current, state)
            if delta is not None:
                deltas.append(delta)
        return deltas

    def flush_remaining(self, state: SessionState) -> list[dict]:
        remaining = [
            item
            for item in state.displayed_sentences
            if not state.formatted_doc.has_sentence(item["id"])
        ]
        return self.flush_window(remaining, state)

    def build_patches(
        self, applied_corrections: list[dict], state: SessionState
    ) -> list[dict]:
        patches: list[dict] = []
        sentence_map = {item["id"]: item for item in state.displayed_sentences}

        for item in applied_corrections:
            target_id = item.get("target_id")
            if not target_id or not state.formatted_doc.has_sentence(target_id):
                continue

            slot = state.formatted_doc.get_slot(target_id)
            current = sentence_map.get(target_id)
            if slot is None or current is None:
                continue
            if current.get("version") != item.get("new_version"):
                continue

            normalized = self.normalize_text(
                current.get("translation", ""),
                state.running_summary.term_map,
            )
            old_text = slot.normalized
            slot.normalized = normalized
            slot.version = int(item.get("new_version", slot.version))

            patches.append(
                {
                    "type": "formatted_patch",
                    "target_id": target_id,
                    "base_version": item.get("base_version"),
                    "new_version": item.get("new_version"),
                    "paragraph_id": slot.paragraph_id,
                    "old_text": old_text,
                    "new_text": normalized,
                    "reason": item.get("reason", ""),
                }
            )
        return patches

    def build_snapshot_payload(self, state: SessionState) -> dict:
        return {
            "type": "formatted_snapshot",
            "paragraphs": state.formatted_doc.build_snapshot(),
            "updated_at_sentence": state.sentence_count,
        }

    def _append_sentence(self, sentence: dict, state: SessionState) -> dict | None:
        translation = sentence.get("translation", "")
        if not translation.strip():
            return None

        normalized = self.normalize_text(translation, state.running_summary.term_map)
        paragraph_id, is_new = self._resolve_paragraph(sentence, state)

        slot = FormatSlot(
            sentence_id=sentence["id"],
            version=int(sentence.get("version", 1)),
            normalized=normalized,
            paragraph_id=paragraph_id,
        )
        state.formatted_doc.slots.append(slot)

        return {
            "type": "formatted_delta",
            "sentence_id": sentence["id"],
            "version": slot.version,
            "paragraph_id": paragraph_id,
            "paragraph_index": state.formatted_doc.paragraph_index(paragraph_id),
            "text": normalized,
            "is_new_paragraph": is_new,
        }

    def _resolve_paragraph(self, sentence: dict, state: SessionState) -> tuple[str, bool]:
        doc = state.formatted_doc
        if not doc.slots:
            self._paragraph_seq += 1
            return f"p_{self._paragraph_seq:03d}", True

        prev = doc.slots[-1]
        prev_sentence = self._find_sentence(prev.sentence_id, state)
        gap_ms = sentence.get("start_time", 0) - (
            prev_sentence.get("end_time", 0) if prev_sentence else 0
        )
        if gap_ms > PARAGRAPH_GAP_MS:
            self._paragraph_seq += 1
            return f"p_{self._paragraph_seq:03d}", True

        if doc.sentences_in_paragraph(prev.paragraph_id) >= MAX_SENTENCES_PER_PARAGRAPH:
            self._paragraph_seq += 1
            return f"p_{self._paragraph_seq:03d}", True

        return prev.paragraph_id, False

    @staticmethod
    def _find_sentence(sentence_id: str, state: SessionState) -> dict | None:
        for item in state.displayed_sentences:
            if item.get("id") == sentence_id:
                return item
        return None

    @staticmethod
    def normalize_text(text: str, term_map: dict[str, str]) -> str:
        result = text.strip()
        if not result:
            return result

        result = re.sub(r"\s+", " ", result)
        for pattern, replacement in NUMBER_REPLACEMENTS:
            result = pattern.sub(replacement, result)

        for source, target in term_map.items():
            if source and target:
                result = result.replace(source, target)
                result = result.replace(target, target)

        for en, zh in term_map.items():
            if en and zh and en.lower() != zh.lower():
                result = re.sub(re.escape(en), zh, result, flags=re.I)

        return TextFormatter._finalize_punctuation(result)

    @staticmethod
    def _finalize_punctuation(text: str) -> str:
        result = text
        if not result:
            return result

        # 仅转换常见半角标点；不把 '.' 转为 '。'，避免破坏英文缩写与数字
        result = (
            result.replace(",", "，")
            .replace("!", "！")
            .replace("?", "？")
            .replace(";", "；")
            .replace(":", "：")
        )

        # 清理 AST 流式译文常见的错误组合
        result = re.sub(r"[，、；]+([。！？])", r"\1", result)
        result = re.sub(r"，。", "。", result)
        result = re.sub(r"、。", "。", result)
        result = re.sub(r"（，", "（", result)
        result = re.sub(r"[，、]{2,}", "，", result)
        result = re.sub(r"[。！？]{2,}", "。", result)

        result = result.rstrip(WEAK_TRAILING)
        if not result:
            return result

        if not result.endswith(PUNCT_ENDINGS):
            result = f"{result}。"

        return result
