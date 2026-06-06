import json
import tempfile
import unittest
from pathlib import Path

from backend.memory.memory_entry import MemoryEntry
from backend.persist.session_reader import SessionReader
from backend.persist.session_writer import SessionWriter
from backend.state.session_state import SessionPhase, SessionState
from backend.summary.running_summary import RunningSummary


class SessionWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_root = SessionWriter.ROOT
        SessionWriter.ROOT = Path(self.temp_dir.name) / "sessions"
        SessionReader.ROOT = SessionWriter.ROOT

    def tearDown(self) -> None:
        SessionWriter.ROOT = self.original_root
        SessionReader.ROOT = self.original_root
        self.temp_dir.cleanup()

    def _build_state(self, session_id: str = "test-session") -> SessionState:
        session_dir = SessionWriter.ensure_session_dir(session_id, started_at=1000.0)
        state = SessionState(
            session_id=session_id,
            started_at=1000.0,
            session_dir=session_dir,
            phase=SessionPhase.RUNNING,
            sentence_count=2,
            correction_count=1,
            merge_count=1,
            ast_fragment_count=3,
        )
        state.running_summary = RunningSummary(
            topic="新能源项目",
            term_map={"new energy project": "新能源项目"},
            bullet_points=["聚焦储能"],
        )
        state.displayed_sentences = [
            {
                "id": "d_001",
                "version": 1,
                "source": "We discuss new energy project",
                "translation": "我们讨论新能源项目",
            }
        ]
        state.formatted_doc.slots = []
        state.memory_entries = [
            MemoryEntry(
                sentence_id="d_001",
                source="We discuss new energy project",
                translation="我们讨论新能源项目",
                version=1,
                correction_hints=["reason: 术语统一"],
                recorded_at=1001.0,
            )
        ]
        return state

    def test_ensure_session_dir(self) -> None:
        session_dir = SessionWriter.ensure_session_dir("abc", started_at=123.0)
        self.assertTrue(session_dir.exists())
        meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["session_id"], "abc")
        self.assertEqual(meta["started_at"], 123.0)

    def test_append_correction(self) -> None:
        session_dir = SessionWriter.ensure_session_dir("corr")
        SessionWriter.append_correction(
            session_dir,
            {"ts": 1.0, "sentence_id": "d_001", "reason": "术语统一"},
        )
        SessionWriter.append_correction(
            session_dir,
            {"ts": 2.0, "sentence_id": "d_002", "reason": "标点"},
        )
        lines = (session_dir / "corrections.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("术语统一", lines[0])

    def test_write_session_state(self) -> None:
        state = self._build_state()
        from backend.format.formatted_document import FormatSlot

        state.formatted_doc.slots = [
            FormatSlot(
                sentence_id="d_001",
                version=1,
                normalized="我们讨论新能源项目。",
                paragraph_id="p_001",
            )
        ]

        path = SessionWriter.write_session_state(state)
        self.assertIsNotNone(path)
        assert path is not None
        self.assertTrue(path.exists())

        markdown = path.read_text(encoding="utf-8")
        self.assertIn("# Session test-session", markdown)
        self.assertIn("新能源项目", markdown)
        self.assertIn("We discuss new energy project", markdown)

        meta = json.loads((state.session_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["topic"], "新能源项目")
        self.assertEqual(meta["sentence_count"], 2)
        self.assertGreater(meta["stopped_at"], 0)

        detail = json.loads((state.session_dir / "session-detail.json").read_text(encoding="utf-8"))
        self.assertEqual(len(detail["sentences"]), 1)
        self.assertEqual(state.phase, SessionPhase.STOPPED)

    def test_write_session_state_empty(self) -> None:
        session_dir = SessionWriter.ensure_session_dir("empty")
        state = SessionState(
            session_id="empty",
            started_at=1000.0,
            session_dir=session_dir,
        )
        path = SessionWriter.write_session_state(state)
        self.assertIsNotNone(path)
        markdown = (session_dir / "SESSION-STATE.md").read_text(encoding="utf-8")
        self.assertIn("sentence_count: 0", markdown)

    def test_write_archive_fallback(self) -> None:
        session_dir = SessionWriter.ensure_session_dir("fallback")
        payload = {"session_id": "fallback", "summary": {"topic": "测试"}}
        path = SessionWriter.write_archive_fallback(session_dir, payload)
        self.assertTrue(path.exists())
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["session_id"], "fallback")


class SessionReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_writer_root = SessionWriter.ROOT
        self.original_reader_root = SessionReader.ROOT
        SessionWriter.ROOT = Path(self.temp_dir.name) / "sessions"
        SessionReader.ROOT = SessionWriter.ROOT

    def tearDown(self) -> None:
        SessionWriter.ROOT = self.original_writer_root
        SessionReader.ROOT = self.original_reader_root
        self.temp_dir.cleanup()

    def test_list_and_get_session(self) -> None:
        state = SessionState(
            session_id="s1",
            started_at=1000.0,
            session_dir=SessionWriter.ensure_session_dir("s1", started_at=1000.0),
            sentence_count=1,
        )
        state.running_summary.topic = "主题一"
        state.displayed_sentences = [
            {"id": "d_001", "version": 1, "source": "Hello", "translation": "你好"}
        ]
        SessionWriter.write_session_state(state)

        state2 = SessionState(
            session_id="s2",
            started_at=900.0,
            session_dir=SessionWriter.ensure_session_dir("s2", started_at=900.0),
            sentence_count=3,
        )
        state2.running_summary.topic = "主题二"
        SessionWriter.write_session_state(state2)

        sessions = SessionReader.list_sessions()
        self.assertEqual(len(sessions), 2)
        session_ids = {item["session_id"] for item in sessions}
        self.assertEqual(session_ids, {"s1", "s2"})

        detail = SessionReader.get_session("s1")
        assert detail is not None
        self.assertEqual(detail["summary"]["topic"], "主题一")
        self.assertEqual(len(detail["sentences"]), 1)
        self.assertIn("# Session s1", detail["raw_markdown"])

    def test_get_session_missing(self) -> None:
        self.assertIsNone(SessionReader.get_session("missing"))


if __name__ == "__main__":
    unittest.main()
