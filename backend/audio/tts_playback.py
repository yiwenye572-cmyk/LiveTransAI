import logging
import queue
import threading
from dataclasses import dataclass, field

import numpy as np

from backend.audio.capture import AudioCaptureError, get_speaker_by_id

logger = logging.getLogger(__name__)


@dataclass
class _SentenceBuffer:
    chunks: list[bytes] = field(default_factory=list)


class TtsPlayback:
    """Play AST s2s PCM chunks on a dedicated output speaker (separate from loopback)."""

    def __init__(
        self,
        speaker_id: str,
        sample_rate: int = 24000,
        audio_format: str = "pcm",
    ) -> None:
        self.speaker_id = speaker_id
        self.sample_rate = sample_rate
        self.audio_format = audio_format
        self._enabled = True
        self._buffers: dict[int, _SentenceBuffer] = {}
        self._queue: queue.Queue[tuple[int, bytes] | None] = queue.Queue(maxsize=32)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._clear_pending()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        self._buffers.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def on_tts_start(self, sequence: int) -> None:
        self._buffers[sequence] = _SentenceBuffer()

    def on_tts_audio(self, sequence: int, audio_data: bytes) -> None:
        if not audio_data:
            return
        buffer = self._buffers.get(sequence)
        if buffer is None:
            buffer = _SentenceBuffer()
            self._buffers[sequence] = buffer
        buffer.chunks.append(audio_data)

    def on_tts_end(self, sequence: int) -> None:
        if not self._enabled:
            self._buffers.pop(sequence, None)
            return

        buffer = self._buffers.pop(sequence, None)
        if buffer is None or not buffer.chunks:
            return

        pcm = b"".join(buffer.chunks)
        try:
            self._queue.put((sequence, pcm), timeout=1)
        except queue.Full:
            logger.warning("TTS playback queue full; dropping sequence %s", sequence)

    def _clear_pending(self) -> None:
        self._buffers.clear()
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if item is None:
                    self._queue.put(None)
                    break
            except queue.Empty:
                break

    def _decode_pcm(self, pcm: bytes) -> np.ndarray:
        if self.audio_format == "pcm":
            samples = np.frombuffer(pcm, dtype="<f4")
            if samples.size == 0:
                return samples.reshape(0, 1)
            return samples.reshape(-1, 1)

        raise AudioCaptureError(f"Unsupported TTS audio format for backend playback: {self.audio_format}")

    def _playback_loop(self) -> None:
        from backend.audio.capture import _initialize_com, _uninitialize_com

        _initialize_com()
        try:
            speaker = get_speaker_by_id(self.speaker_id)
            with speaker.player(samplerate=self.sample_rate, channels=1) as player:
                while not self._stop.is_set():
                    try:
                        item = self._queue.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    if item is None:
                        break

                    _sequence, pcm = item
                    if not self._enabled:
                        continue

                    try:
                        samples = self._decode_pcm(pcm)
                        if samples.size == 0:
                            continue
                        player.play(samples)
                    except Exception as exc:
                        logger.exception("TTS playback failed: %s", exc)
        except Exception as exc:
            logger.exception("TTS playback thread failed: %s", exc)
        finally:
            _uninitialize_com()
