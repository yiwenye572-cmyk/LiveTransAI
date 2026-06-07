from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionReader:
    ROOT = Path("data/sessions")

    @classmethod
    def list_sessions(cls) -> list[dict]:
        if not cls.ROOT.exists():
            return []

        items: list[dict] = []
        for session_dir in cls.ROOT.iterdir():
            if not session_dir.is_dir():
                continue
            meta_path = session_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.exception("Failed to read session meta: %s", meta_path)
                continue
            if meta.get("stopped_at", 0.0):
                items.append(meta)

        items.sort(key=lambda item: item.get("stopped_at", 0.0), reverse=True)
        return items

    @classmethod
    def get_session(cls, session_id: str) -> dict | None:
        session_dir = cls.ROOT / session_id
        if not session_dir.is_dir():
            return None

        meta = cls._read_json(session_dir / "meta.json")
        if meta is None:
            return None

        detail = cls._read_json(session_dir / "session-detail.json")
        raw_markdown = cls._read_text(session_dir / "SESSION-STATE.md")

        if detail is None:
            return {
                "meta": meta,
                "summary": {
                    "topic": meta.get("topic", ""),
                    "term_map": {},
                    "bullet_points": [],
                },
                "formatted": {"paragraphs": [meta.get("preview_zh", "")] if meta.get("preview_zh") else []},
                "sentences": [],
                "memory_entries": [],
                "raw_markdown": raw_markdown or "",
            }

        summary = detail.get("summary", {})
        sentences = cls._merge_correction_records(session_dir, detail.get("sentences", []))
        return {
            "meta": meta,
            "summary": {
                "topic": summary.get("topic", ""),
                "term_map": summary.get("term_map", {}),
                "bullet_points": summary.get("bullet_points", []),
            },
            "formatted": {"paragraphs": detail.get("formatted_paragraphs", [])},
            "sentences": sentences,
            "memory_entries": detail.get("memory_entries", []),
            "raw_markdown": raw_markdown or "",
        }

    @classmethod
    def _merge_correction_records(cls, session_dir: Path, sentences: list) -> list[dict]:
        if not isinstance(sentences, list):
            return []

        merged = [dict(item) for item in sentences if isinstance(item, dict)]
        corrections_path = session_dir / "corrections.jsonl"
        if not corrections_path.exists():
            return merged

        latest_by_sentence: dict[str, dict] = {}
        try:
            for line in corrections_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    continue
                sentence_id = str(record.get("sentence_id", "") or "")
                if sentence_id:
                    latest_by_sentence[sentence_id] = record
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read corrections: %s", corrections_path)
            return merged

        for item in merged:
            sentence_id = str(item.get("id", "") or "")
            record = latest_by_sentence.get(sentence_id)
            if record is None:
                continue

            version = int(item.get("version", 1))
            old_translation = str(item.get("old_translation", "") or record.get("old_translation", "") or "")
            new_translation = str(record.get("new_translation", "") or item.get("translation", "") or "")
            new_version = int(record.get("new_version", version) or version)

            if new_translation:
                item["translation"] = new_translation
            item["version"] = max(version, new_version)
            if old_translation:
                item["old_translation"] = old_translation
            reason = str(item.get("reason", "") or record.get("reason", "") or "")
            if reason:
                item["reason"] = reason
            if item["version"] > 1 or item.get("old_translation"):
                item["confidence"] = "corrected"

        return merged

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read JSON: %s", path)
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _read_text(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            logger.exception("Failed to read text: %s", path)
            return None
