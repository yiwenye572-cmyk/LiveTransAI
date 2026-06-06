import unittest
from unittest.mock import MagicMock

from backend.audio.capture import LoopbackCapture
from backend.server.ws_server import ConnectionManager, TranslationSession
from backend.state.session_state import SessionPhase, SessionState


class LoopbackCapturePauseTests(unittest.TestCase):
    def test_pause_resume_flags(self) -> None:
        capture = LoopbackCapture.__new__(LoopbackCapture)
        capture._paused = __import__("threading").Event()

        self.assertFalse(capture.is_paused)
        capture.pause()
        self.assertTrue(capture.is_paused)
        capture.resume()
        self.assertFalse(capture.is_paused)


class TranslationSessionPauseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.manager = ConnectionManager()
        self.session = TranslationSession(self.manager)
        self.session.state_label = "speaking"
        self.session._session_state = SessionState(phase=SessionPhase.RUNNING)
        self.mock_capture = MagicMock()
        self.session._capture = self.mock_capture
        self.broadcasts: list[dict] = []
        self.manager.broadcast = self._capture_broadcast

    async def _capture_broadcast(self, message: dict) -> None:
        self.broadcasts.append(message)

    async def test_pause_from_speaking(self) -> None:
        await self.session.pause()

        self.assertEqual(self.session.state_label, "paused")
        assert self.session._session_state is not None
        self.assertEqual(self.session._session_state.phase, SessionPhase.PAUSED)
        self.mock_capture.pause.assert_called_once()
        self.assertEqual(self.broadcasts[-1], {"type": "status", "state": "paused", "reason": "user"})

    async def test_pause_is_noop_when_not_speaking(self) -> None:
        self.session.state_label = "ready"
        await self.session.pause()
        self.mock_capture.pause.assert_not_called()
        self.assertEqual(self.broadcasts, [])

    async def test_resume_from_paused(self) -> None:
        self.session.state_label = "paused"
        self.session._session_state.phase = SessionPhase.PAUSED

        await self.session.resume()

        self.assertEqual(self.session.state_label, "speaking")
        assert self.session._session_state is not None
        self.assertEqual(self.session._session_state.phase, SessionPhase.RUNNING)
        self.mock_capture.resume.assert_called_once()
        self.assertEqual(self.broadcasts[-1], {"type": "status", "state": "speaking"})

    async def test_resume_is_noop_when_not_paused(self) -> None:
        await self.session.resume()
        self.mock_capture.resume.assert_not_called()
        self.assertEqual(self.broadcasts, [])


if __name__ == "__main__":
    unittest.main()
