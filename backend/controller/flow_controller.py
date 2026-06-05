import asyncio
import logging
import time

from backend.bus.subtitle_bus import SubtitleBus
from backend.correction.engine import CorrectionEngine
from backend.state.session_state import SessionState

logger = logging.getLogger(__name__)


class FlowController:
    """Minimal flow control: pass-through display + periodic correction trigger."""

    MIN_SENTENCES = 3
    MIN_INTERVAL_SEC = 8.0
    CORRECTION_WINDOW = 8

    def __init__(
        self,
        state: SessionState,
        bus: SubtitleBus,
        correction_engine: CorrectionEngine,
    ) -> None:
        self.state = state
        self.bus = bus
        self.correction_engine = correction_engine
        self._last_correction_time = 0.0
        self._correction_running = False

    async def on_new_sentence(self, sentence: dict) -> None:
        record = dict(sentence)
        self.state.displayed_sentences.append(record)
        self.state.sentence_count += 1
        await self.bus.publish("commit_display", sentence)

        if self._should_trigger_correction():
            self._last_correction_time = time.time()
            asyncio.create_task(self._run_correction())

    def _should_trigger_correction(self) -> bool:
        if not self.correction_engine.enabled:
            return False
        if len(self.state.displayed_sentences) < self.MIN_SENTENCES:
            return False
        if time.time() - self._last_correction_time < self.MIN_INTERVAL_SEC:
            return False
        if self._correction_running:
            return False
        return True

    async def _run_correction(self) -> None:
        self._correction_running = True
        try:
            window = self.state.displayed_sentences[-self.CORRECTION_WINDOW :]
            corrections = await self.correction_engine.run(window)
            for item in corrections:
                if not self._apply_correction(item):
                    continue
                self.state.correction_count += 1
                await self.bus.publish("correction", item)
        except Exception:
            logger.exception("Correction run failed")
        finally:
            self._correction_running = False

    def _apply_correction(self, item: dict) -> bool:
        target_id = item.get("target_id")
        base_version = item.get("base_version")
        new_translation = item.get("new_translation")
        new_version = item.get("new_version")

        for sentence in self.state.displayed_sentences:
            if sentence.get("id") != target_id:
                continue
            if sentence.get("version") != base_version:
                return False
            sentence["translation"] = new_translation
            sentence["version"] = new_version
            return True
        return False
