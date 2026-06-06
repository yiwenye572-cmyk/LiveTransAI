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
        return {
            "meta": meta,
            "summary": {
                "topic": summary.get("topic", ""),
                "term_map": summary.get("term_map", {}),
                "bullet_points": summary.get("bullet_points", []),
            },
            "formatted": {"paragraphs": detail.get("formatted_paragraphs", [])},
            "sentences": detail.get("sentences", []),
            "memory_entries": detail.get("memory_entries", []),
            "raw_markdown": raw_markdown or "",
        }

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
