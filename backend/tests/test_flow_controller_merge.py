import time
import unittest
from unittest.mock import AsyncMock

from backend.bus.subtitle_bus import SubtitleBus
from backend.controller.flow_controller import FlowController
from backend.correction.engine import CorrectionEngine
from backend.state.session_state import SessionState
from backend.summary.updater import SummaryUpdater


def _fragment(
    source: str,
    *,
    fid: str = "s_001",
    translation: str = "译文",
    received_at: float | None = None,
    start_time: int = 0,
    end_time: int = 1000,
) -> dict:
    return {
        "type": "subtitle",
        "id": fid,
        "version": 1,
        "speaker": "speaker",
        "source": source,
        "translation": translation,
        "received_at": received_at if received_at is not None else time.time(),
        "start_time": start_time,
        "end_time": end_time,
        "ast_sequence": 1,
    }


def _build_controller() -> FlowController:
    state = SessionState()
    bus = SubtitleBus()
    correction = CorrectionEngine(None)
    summary = SummaryUpdater(None)
    return FlowController(state, bus, correction, summary)


class ShouldCommitNowTests(unittest.TestCase):
    def test_short_sentence_not_timed_out(self) -> None:
        flow = _build_controller()
        flow.pending.append(_fragment("one two three", received_at=time.time() - 0.1))
        self.assertFalse(flow._should_commit_now())

    def test_short_sentence_timed_out(self) -> None:
        flow = _build_controller()
        flow.pending.append(_fragment("one two three", received_at=time.time() - 0.35))
        self.assertTrue(flow._should_commit_now())

    def test_long_sentence_immediate(self) -> None:
        flow = _build_controller()
        flow.pending.append(
            _fragment("one two three four five six seven eight", received_at=time.time())
        )
        self.assertTrue(flow._should_commit_now())

    def test_adjacent_fragments_phase_b(self) -> None:
        flow = _build_controller()
        base = time.time() - 0.2
        flow.pending.append(
            _fragment("We use", fid="s_001", received_at=base, start_time=0, end_time=500)
        )
        flow.pending.append(
            _fragment(
                "federated learning",
                fid="s_002",
                received_at=time.time(),
                start_time=600,
                end_time=1200,
            )
        )
        self.assertFalse(flow._should_commit_now())


class MergePendingTests(unittest.TestCase):
    def test_merge_source_and_translation(self) -> None:
        flow = _build_controller()
        flow.pending.append(
            _fragment("We use", fid="s_001", translation="我们使用", start_time=0, end_time=500)
        )
        flow.pending.append(
            _fragment(
                "federated learning",
                fid="s_002",
                translation="联邦学习",
                start_time=600,
                end_time=1200,
            )
        )
        merged = flow._merge_pending()
        self.assertEqual(merged["source"], "We use federated learning")
        self.assertEqual(merged["translation"], "我们使用联邦学习")
        self.assertEqual(merged["id"], "d_001")
        self.assertEqual(merged["merged_from"], ["s_001", "s_002"])


class FlushPendingTests(unittest.IsolatedAsyncioTestCase):
    async def test_flush_commits_pending(self) -> None:
        flow = _build_controller()
        published: list[dict] = []

        async def capture(payload: dict) -> None:
            published.append(payload)

        flow.bus.subscribe("commit_display", capture)
        flow.pending.append(_fragment("hello world today", received_at=time.time()))

        await flow.flush_pending()

        self.assertEqual(len(flow.pending), 0)
        self.assertEqual(flow.state.sentence_count, 1)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["id"], "d_001")

    async def test_merge_count_increments(self) -> None:
        flow = _build_controller()
        flow.bus.subscribe("commit_display", AsyncMock())
        flow.pending.append(_fragment("We use", fid="s_001"))
        flow.pending.append(
            _fragment("federated learning", fid="s_002", start_time=600, end_time=1200)
        )

        await flow.flush_pending()

        self.assertEqual(flow.state.merge_count, 1)
        self.assertEqual(flow.state.sentence_count, 1)


if __name__ == "__main__":
    unittest.main()
