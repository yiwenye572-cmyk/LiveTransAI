from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from backend.state.session_state import SessionPhase, SessionState

logger = logging.getLogger(__name__)

PREVIEW_ZH_LIMIT = 120


class SessionWriter:
    ROOT = Path("data/sessions")

    @classmethod
    def ensure_session_dir(cls, session_id: str, *, started_at: float | None = None) -> Path:
        session_dir = cls.ROOT / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        started = started_at if started_at is not None else time.time()
        meta = {
            "session_id": session_id,
            "started_at": started,
            "stopped_at": 0.0,
            "topic": "",
            "sentence_count": 0,
            "correction_count": 0,
            "term_count": 0,
            "preview_zh": "",
        }
        cls._write_json(session_dir / "meta.json", meta)
        return session_dir

    @classmethod
    def append_correction(cls, session_dir: Path, record: dict) -> None:
        path = session_dir / "corrections.jsonl"
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("Failed to append correction to %s", path)

    @classmethod
    def write_session_state(cls, state: SessionState) -> Path | None:
        if not state.session_dir:
            return None

        state.stopped_at = time.time()
        state.phase = SessionPhase.STOPPED
        payload = cls.build_snapshot_dict(state)
        session_dir = state.session_dir

        try:
            markdown = cls.render_markdown(payload)
            (session_dir / "SESSION-STATE.md").write_text(markdown, encoding="utf-8")
            cls._write_json(session_dir / "session-detail.json", payload)
            cls._write_json(session_dir / "meta.json", cls.build_meta(payload))
            return session_dir / "SESSION-STATE.md"
        except OSError:
            logger.exception("Failed to write SESSION-STATE.md for %s", state.session_id)
            cls.write_archive_fallback(session_dir, payload)
            return None

    @classmethod
    def write_archive_fallback(cls, session_dir: Path, payload: dict) -> Path:
        archive_dir = session_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        path = archive_dir / f"session-state-{ts}.json"
        cls._write_json(path, payload)
        return path

    @classmethod
    def build_snapshot_dict(cls, state: SessionState) -> dict:
        paragraphs = state.formatted_doc.build_snapshot()
        return {
            "session_id": state.session_id,
            "started_at": state.started_at,
            "stopped_at": state.stopped_at or time.time(),
            "sentence_count": state.sentence_count,
            "correction_count": state.correction_count,
            "merge_count": state.merge_count,
            "ast_fragment_count": state.ast_fragment_count,
            "summary": {
                "topic": state.running_summary.topic,
                "term_map": dict(state.running_summary.term_map),
                "bullet_points": list(state.running_summary.bullet_points),
            },
            "formatted_paragraphs": paragraphs,
            "sentences": [
                {
                    "id": item.get("id", ""),
                    "version": int(item.get("version", 1)),
                    "source": item.get("source", ""),
                    "translation": item.get("translation", ""),
                }
                for item in state.displayed_sentences
            ],
            "memory_entries": [asdict(entry) for entry in state.memory_entries],
        }

    @classmethod
    def build_meta(cls, payload: dict) -> dict:
        summary = payload.get("summary", {})
        paragraphs = payload.get("formatted_paragraphs", [])
        preview = paragraphs[0][:PREVIEW_ZH_LIMIT] if paragraphs else ""
        term_map = summary.get("term_map", {})
        return {
            "session_id": payload.get("session_id", ""),
            "started_at": payload.get("started_at", 0.0),
            "stopped_at": payload.get("stopped_at", 0.0),
            "topic": summary.get("topic", ""),
            "sentence_count": payload.get("sentence_count", 0),
            "correction_count": payload.get("correction_count", 0),
            "term_count": len(term_map) if isinstance(term_map, dict) else 0,
            "preview_zh": preview,
        }

    @classmethod
    def render_markdown(cls, payload: dict) -> str:
        summary = payload.get("summary", {})
        topic = summary.get("topic", "")
        term_map = summary.get("term_map", {})
        bullets = summary.get("bullet_points", [])
        paragraphs = payload.get("formatted_paragraphs", [])
        sentences = payload.get("sentences", [])
        memory_entries = payload.get("memory_entries", [])

        lines = [
            f"# Session {payload.get('session_id', '')}",
            "",
            f"- started_at: {cls._format_ts(payload.get('started_at', 0.0))}",
            f"- stopped_at: {cls._format_ts(payload.get('stopped_at', 0.0))}",
            f"- sentence_count: {payload.get('sentence_count', 0)}",
            f"- correction_count: {payload.get('correction_count', 0)}",
            f"- merge_count: {payload.get('merge_count', 0)}",
            f"- ast_fragment_count: {payload.get('ast_fragment_count', 0)}",
            "",
            "## Summary",
            "",
            f"**Topic:** {topic or '—'}",
            "",
            "**Terms:**",
        ]

        if term_map:
            for source, target in term_map.items():
                lines.append(f"- {source} → {target}")
        else:
            lines.append("- —")

        lines.extend(["", "**Bullets:**"])
        if bullets:
            lines.extend(f"- {point}" for point in bullets)
        else:
            lines.append("- —")

        lines.extend(["", "## Formatted Text (ZH)", ""])
        if paragraphs:
            lines.extend(paragraphs)
        else:
            lines.append("（无规整译文）")

        lines.extend(["", "## Sentences", "", "| id | version | EN | ZH |", "|----|---------|----|----|"])
        for item in sentences:
            row_id = cls._escape_md_cell(item.get("id", ""))
            version = str(item.get("version", 1))
            source = cls._escape_md_cell(item.get("source", ""))
            translation = cls._escape_md_cell(item.get("translation", ""))
            lines.append(f"| {row_id} | {version} | {source} | {translation} |")

        if memory_entries:
            lines.extend(["", "## Memory", ""])
            for entry in memory_entries:
                hints = entry.get("correction_hints", [])
                hint_text = "；".join(hints) if hints else "—"
                lines.append(
                    f"- {entry.get('sentence_id', '')}: "
                    f"{entry.get('source', '')} / {entry.get('translation', '')} "
                    f"({hint_text})"
                )

        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_ts(value: float) -> str:
        if not value:
            return "—"
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _escape_md_cell(text: str) -> str:
        return str(text).replace("|", "\\|").replace("\n", " ")

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
