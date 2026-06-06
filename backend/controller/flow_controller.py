import asyncio
import logging
import time

from backend.bus.subtitle_bus import SubtitleBus
from backend.correction.engine import CorrectionEngine
from backend.format.text_formatter import TextFormatter
from backend.memory.memory_store import MemoryStore
from backend.persist.session_writer import SessionWriter
from backend.state.session_state import SessionState
from backend.summary.updater import SummaryUpdater

logger = logging.getLogger(__name__)


class FlowController:
    """Lookahead merge + display with parallel incremental summary and correction."""

    MIN_SENTENCES = 3
    MIN_INTERVAL_SEC = 8.0
    CORRECTION_WINDOW = 8
    SUMMARY_EVERY_N = 5

    MIN_WAIT_MS = 300
    MAX_WAIT_MS = 800
    SHORT_WORD_THRESHOLD = 5
    GAP_MERGE_MS = 200

    def __init__(
        self,
        state: SessionState,
        bus: SubtitleBus,
        correction_engine: CorrectionEngine,
        summary_updater: SummaryUpdater,
        text_formatter: TextFormatter | None = None,
        memory_store: MemoryStore | None = None,
        session_writer: type[SessionWriter] | None = None,
    ) -> None:
        self.state = state
        self.bus = bus
        self.correction_engine = correction_engine
        self.summary_updater = summary_updater
        self.text_formatter = text_formatter or TextFormatter()
        self.memory_store = memory_store or MemoryStore()
        self.session_writer = session_writer or SessionWriter
        self.pending: list[dict] = []
        self._display_seq = 0
        self._commit_timer: asyncio.Task | None = None
        self._last_correction_time = 0.0
        self._last_format_flush_time = 0.0
        self._correction_running = False
        self._summary_running = False

    async def on_new_sentence(self, fragment: dict) -> None:
        self.state.ast_fragment_count += 1
        self.pending.append(dict(fragment))

        if self._should_commit_now():
            await self._commit_pending()
        else:
            await self._schedule_delayed_commit()

    async def flush_pending(self) -> None:
        if not self.pending:
            return
        await self._commit_pending()

    async def finalize_session(self) -> dict | None:
        deltas = self.text_formatter.flush_remaining(self.state)
        for delta in deltas:
            await self.bus.publish("formatted_delta", delta)
        if not self.state.formatted_doc.slots:
            return None
        snapshot = self.text_formatter.build_snapshot_payload(self.state)
        await self.bus.publish("formatted_snapshot", snapshot)
        return snapshot

    def _should_commit_now(self) -> bool:
        if not self.pending:
            return False

        first = self.pending[0]
        waited_ms = (time.time() - first["received_at"]) * 1000

        if waited_ms >= self.MAX_WAIT_MS:
            return True

        if len(self.pending) == 1:
            source_words = len(first.get("source", "").split())
            if source_words < self.SHORT_WORD_THRESHOLD and waited_ms < self.MIN_WAIT_MS:
                return False
            return True

        last = self.pending[-1]
        prev = self.pending[-2]

        gap_ms = last.get("start_time", 0) - prev.get("end_time", 0)
        if gap_ms < self.GAP_MERGE_MS:
            return False

        prev_words = len(prev.get("source", "").split())
        if prev_words < self.SHORT_WORD_THRESHOLD and waited_ms < self.MAX_WAIT_MS:
            return False

        return True

    def _sleep_until_commit_ms(self) -> float:
        if not self.pending:
            return 0.0

        first = self.pending[0]
        waited_ms = (time.time() - first["received_at"]) * 1000
        remaining_max = max(0.0, self.MAX_WAIT_MS - waited_ms)

        if len(self.pending) == 1:
            words = len(first.get("source", "").split())
            if words < self.SHORT_WORD_THRESHOLD:
                remaining_min = max(0.0, self.MIN_WAIT_MS - waited_ms)
                if remaining_min > 0:
                    return min(remaining_min, remaining_max)

        return remaining_max

    async def _schedule_delayed_commit(self) -> None:
        if self._commit_timer and not self._commit_timer.done():
            self._commit_timer.cancel()
            try:
                await self._commit_timer
            except asyncio.CancelledError:
                pass

        self._commit_timer = asyncio.create_task(self._delayed_commit())

    async def _delayed_commit(self) -> None:
        try:
            sleep_ms = self._sleep_until_commit_ms()
            if sleep_ms <= 0:
                if self.pending and self._should_commit_now():
                    await self._commit_pending()
                return

            await asyncio.sleep(sleep_ms / 1000)
            if not self.pending:
                return
            if self._should_commit_now():
                await self._commit_pending()
            else:
                await self._schedule_delayed_commit()
        except asyncio.CancelledError:
            return

    def _merge_pending(self) -> dict:
        source = " ".join(
            p["source"].strip() for p in self.pending if p.get("source", "").strip()
        )
        translation = "".join(p.get("translation", "") for p in self.pending)
        self._display_seq += 1
        merged_from = [p["id"] for p in self.pending]
        first = self.pending[0]
        last = self.pending[-1]

        return {
            "type": "subtitle",
            "id": f"d_{self._display_seq:03d}",
            "version": 1,
            "speaker": first.get("speaker", "speaker"),
            "source": source,
            "translation": translation,
            "confidence": "fast",
            "merged_from": merged_from,
            "start_time": first.get("start_time", 0),
            "end_time": last.get("end_time", 0),
            "received_at": first.get("received_at", time.time()),
        }

    async def _commit_pending(self) -> None:
        if not self.pending:
            return

        if self._commit_timer and not self._commit_timer.done():
            self._commit_timer.cancel()
            try:
                await self._commit_timer
            except asyncio.CancelledError:
                pass
            self._commit_timer = None

        fragment_count = len(self.pending)
        first = self.pending[0]
        waited_ms = (time.time() - first.get("received_at", time.time())) * 1000
        merged = self._merge_pending()
        word_count = len(merged.get("source", "").split())

        if fragment_count > 1:
            self.state.merge_count += 1

        self.pending.clear()
        self.state.displayed_sentences.append(dict(merged))
        self.state.sentence_count += 1

        commit_time = time.time()
        received_at = float(first.get("received_at", commit_time))
        display_latency_ms = (commit_time - received_at) * 1000.0
        self.state.metrics.record_display_latency(
            sentence_id=merged["id"],
            latency_ms=display_latency_ms,
            merge_count=fragment_count,
            wait_ms=waited_ms,
        )

        logger.info(
            "Committed %s: merged %s fragments %s wait=%.0fms words=%s",
            merged["id"],
            fragment_count,
            merged.get("merged_from", []),
            waited_ms,
            word_count,
        )

        await self.bus.publish("commit_display", merged)

        if self._should_trigger_summary():
            asyncio.create_task(self._run_summary())

        if self._should_trigger_correction():
            self._last_correction_time = time.time()
            asyncio.create_task(self._run_correction())
        elif self._should_trigger_format_flush():
            self._last_format_flush_time = time.time()
            asyncio.create_task(self._run_format_flush())

    def _should_trigger_format_flush(self) -> bool:
        if len(self.state.displayed_sentences) < self.MIN_SENTENCES:
            return False
        if time.time() - self._last_format_flush_time < self.MIN_INTERVAL_SEC:
            return False
        return not self.correction_engine.enabled

    async def _emit_formatted_updates(
        self, window: list[dict], applied_items: list[dict]
    ) -> None:
        patches = self.text_formatter.build_patches(applied_items, self.state)
        for patch in patches:
            await self.bus.publish("formatted_patch", patch)

        deltas = self.text_formatter.flush_window(window, self.state)
        for delta in deltas:
            await self.bus.publish("formatted_delta", delta)

        self.memory_store.append_batch(window, applied_items, self.state)

    async def _run_format_flush(self) -> None:
        window = self.state.displayed_sentences[-self.CORRECTION_WINDOW :]
        await self._emit_formatted_updates(window, [])

    def _should_trigger_summary(self) -> bool:
        if not self.summary_updater.enabled:
            return False
        if self._summary_running:
            return False
        pending = self.state.sentence_count - self.state.running_summary.last_summarized_at
        return pending >= self.SUMMARY_EVERY_N

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

    async def _run_summary(self) -> None:
        self._summary_running = True
        try:
            updated = await self.summary_updater.update(self.state)
            if updated:
                await self.bus.publish(
                    "summary_update",
                    self.state.running_summary.to_ws_payload(
                        sentence_count=self.state.sentence_count,
                    ),
                )
        except Exception:
            logger.exception("Summary run failed")
        finally:
            self._summary_running = False

    async def _run_correction(self) -> None:
        self._correction_running = True
        try:
            window = self.state.displayed_sentences[-self.CORRECTION_WINDOW :]
            summary_snapshot = self.state.running_summary
            corrections = await self.correction_engine.run(
                window, summary_snapshot, self.state
            )
            applied_items: list[dict] = []
            applied = 0
            for item in corrections:
                if not self._apply_correction(item):
                    continue
                self.state.correction_count += 1
                applied += 1
                applied_items.append(item)
                await self.bus.publish("correction", item)
                self._persist_correction(item)

            await self._emit_formatted_updates(window, applied_items)
            logger.info(
                "Correction finished: %s updates at sentence %s",
                applied,
                self.state.sentence_count,
            )
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

    def _persist_correction(self, item: dict) -> None:
        session_dir = self.state.session_dir
        if session_dir is None:
            return

        source = ""
        for sentence in self.state.displayed_sentences:
            if sentence.get("id") == item.get("target_id"):
                source = str(sentence.get("source", ""))
                break

        record = {
            "ts": time.time(),
            "sentence_id": item.get("target_id", ""),
            "base_version": item.get("base_version"),
            "new_version": item.get("new_version"),
            "source": source,
            "old_translation": item.get("old_translation", ""),
            "new_translation": item.get("new_translation", ""),
            "reason": item.get("reason", ""),
            "confidence": item.get("confidence"),
        }
        self.session_writer.append_correction(session_dir, record)
