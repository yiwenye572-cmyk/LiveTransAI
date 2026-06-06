import asyncio
import inspect
import os
import threading
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
import soundcard as sc


class AudioCaptureError(RuntimeError):
    """Raised when the local audio capture device cannot be opened."""


@dataclass(frozen=True)
class AudioCaptureConfig:
    sample_rate: int = 16000
    channels: int = 1
    sample_width_bytes: int = 2
    chunk_ms: int = 80

    @property
    def blocksize(self) -> int:
        return int(self.sample_rate * self.chunk_ms / 1000)


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    kind: str
    id: str = ""


@dataclass(frozen=True)
class WavStats:
    frames: int
    sample_rate: int
    channels: int
    rms: float
    peak: int


def list_audio_devices() -> list[AudioDevice]:
    devices = sd.query_devices()
    sounddevice_devices = [_device_from_raw(index, device, "device") for index, device in enumerate(devices)]
    return _soundcard_loopback_devices() + sounddevice_devices


def get_audio_device(index: int) -> AudioDevice:
    for device in list_audio_devices():
        if device.index == index:
            return device
    raise AudioCaptureError(f"Audio device index not found: {index}")


def find_loopback_device() -> AudioDevice:
    devices = list_audio_devices()

    soundcard_loopbacks = [device for device in devices if device.kind == "soundcard_loopback"]
    if soundcard_loopbacks:
        return soundcard_loopbacks[0]

    named_loopback = [
        device
        for device in devices
        if device.max_input_channels > 0
        and (
            "loopback" in device.name.lower()
            or "blackhole" in device.name.lower()
            or "stereo mix" in device.name.lower()
            or "立体声混音" in device.name
        )
    ]
    if named_loopback:
        return named_loopback[0]

    if _supports_wasapi_loopback_setting():
        default_output = _default_output_device(devices)
        if default_output and _is_wasapi(default_output.hostapi):
            return _mark_as_wasapi_loopback(default_output)

        wasapi_outputs = [
            device
            for device in devices
            if _is_wasapi(device.hostapi) and device.max_output_channels > 0
        ]
        if wasapi_outputs:
            return _mark_as_wasapi_loopback(wasapi_outputs[0])

    microphone = [device for device in devices if device.max_input_channels > 0]
    if microphone:
        return microphone[0]

    raise AudioCaptureError("No usable audio input or WASAPI loopback output device was found.")


def record_wav(
    output_path: Path | str,
    duration_seconds: float,
    config: AudioCaptureConfig | None = None,
    device: AudioDevice | None = None,
) -> Path:
    capture_config = config or AudioCaptureConfig()
    capture_device = device or find_loopback_device()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if capture_device.kind == "soundcard_loopback":
        return _record_soundcard_wav(output, duration_seconds, capture_config, capture_device)

    chunks: list[bytes] = []
    statuses: list[str] = []

    def on_audio(indata: bytes, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            statuses.append(str(status))
        chunks.append(bytes(indata))

    try:
        with sd.RawInputStream(
            device=capture_device.index,
            samplerate=capture_config.sample_rate,
            channels=capture_config.channels,
            dtype="int16",
            blocksize=capture_config.blocksize,
            callback=on_audio,
            extra_settings=_extra_settings_for(capture_device),
        ):
            sd.sleep(int(duration_seconds * 1000))
    except Exception as exc:
        raise AudioCaptureError(f"Failed to record from {capture_device.name}: {exc}") from exc

    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(capture_config.channels)
        wav_file.setsampwidth(capture_config.sample_width_bytes)
        wav_file.setframerate(capture_config.sample_rate)
        wav_file.writeframes(b"".join(chunks))

    if statuses:
        print("Audio callback status:", "; ".join(statuses[-3:]))

    return output


class LoopbackCapture:
    """Stream PCM chunks from a soundcard loopback device."""

    def __init__(
        self,
        config: AudioCaptureConfig | None = None,
        device: AudioDevice | None = None,
    ):
        self.config = config or AudioCaptureConfig()
        self.device = device or find_loopback_device()
        self._queue: asyncio.Queue[bytes | None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._error: Exception | None = None
        self._microphone = None

    async def __aenter__(self) -> "LoopbackCapture":
        if self.device.kind != "soundcard_loopback":
            raise AudioCaptureError("Realtime capture currently requires a soundcard loopback device.")

        self._microphone = _soundcard_microphone_for(self.device)
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=64)
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.stop()
        if self._thread:
            self._thread.join(timeout=3)
        if self._error is not None:
            raise AudioCaptureError(f"Loopback capture failed: {self._error}") from self._error

    def stop(self) -> None:
        self._stop.set()

    async def chunks(self) -> AsyncIterator[bytes]:
        if self._queue is None:
            raise AudioCaptureError("LoopbackCapture is not started.")

        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk

    def _capture_loop(self) -> None:
        assert self._loop is not None
        assert self._queue is not None
        assert self._microphone is not None

        _initialize_com()
        blocksize = self.config.blocksize

        try:
            with self._microphone.recorder(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
            ) as recorder:
                while not self._stop.is_set():
                    samples = recorder.record(numframes=blocksize)
                    samples = _amplify_quiet_loopback(samples)
                    pcm = _float_samples_to_pcm16(samples)
                    future = asyncio.run_coroutine_threadsafe(self._queue.put(pcm), self._loop)
                    future.result(timeout=5)
        except Exception as exc:
            self._error = exc
        finally:
            _uninitialize_com()
            asyncio.run_coroutine_threadsafe(self._queue.put(None), self._loop).result(timeout=5)


def _initialize_com() -> None:
    import ctypes

    result = ctypes.windll.ole32.CoInitializeEx(None, 0)
    if result not in (0, 1):  # S_OK or S_FALSE
        raise AudioCaptureError(f"Failed to initialize COM: {result}")


def _uninitialize_com() -> None:
    import ctypes

    ctypes.windll.ole32.CoUninitialize()


def wav_stats(path: Path | str) -> WavStats:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.getnframes()
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        raw = wav_file.readframes(frames)

    samples = np.frombuffer(raw, dtype="<i2")
    if samples.size == 0:
        return WavStats(frames=frames, sample_rate=sample_rate, channels=channels, rms=0.0, peak=0)

    rms = float(np.sqrt(np.mean(samples.astype("float64") ** 2)))
    peak = int(np.max(np.abs(samples)))
    return WavStats(frames=frames, sample_rate=sample_rate, channels=channels, rms=rms, peak=peak)


def _device_from_raw(index: int, raw: dict[str, Any], kind: str) -> AudioDevice:
    hostapi_index = int(raw.get("hostapi", -1))
    return AudioDevice(
        index=index,
        name=str(raw.get("name", "")),
        hostapi=_hostapi_name(hostapi_index),
        max_input_channels=int(raw.get("max_input_channels", 0)),
        max_output_channels=int(raw.get("max_output_channels", 0)),
        default_samplerate=float(raw.get("default_samplerate", 0)),
        kind=kind,
    )


def _soundcard_loopback_devices() -> list[AudioDevice]:
    try:
        default_speaker = sc.default_speaker()
        microphones = sc.all_microphones(include_loopback=True)
    except Exception:
        return []

    loopbacks = [mic for mic in microphones if getattr(mic, "isloopback", False)]
    if not loopbacks:
        return []

    ordered = sorted(loopbacks, key=lambda mic: 0 if mic.id == default_speaker.id else 1)
    return [
        AudioDevice(
            index=-100 - offset,
            name=mic.name,
            hostapi="soundcard",
            max_input_channels=2,
            max_output_channels=0,
            default_samplerate=48000,
            kind="soundcard_loopback",
            id=mic.id,
        )
        for offset, mic in enumerate(ordered)
    ]


def _record_soundcard_wav(
    output: Path,
    duration_seconds: float,
    config: AudioCaptureConfig,
    device: AudioDevice,
) -> Path:
    microphone = _soundcard_microphone_for(device)
    frames = int(config.sample_rate * duration_seconds)

    try:
        with microphone.recorder(samplerate=config.sample_rate, channels=config.channels) as recorder:
            samples = recorder.record(numframes=frames)
    except Exception as exc:
        raise AudioCaptureError(f"Failed to record from {device.name}: {exc}") from exc

    pcm = _float_samples_to_pcm16(samples)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(config.channels)
        wav_file.setsampwidth(config.sample_width_bytes)
        wav_file.setframerate(config.sample_rate)
        wav_file.writeframes(pcm)

    return output


def _soundcard_microphone_for(device: AudioDevice):
    microphones = sc.all_microphones(include_loopback=True)
    for microphone in microphones:
        if microphone.id == device.id:
            return microphone
    raise AudioCaptureError(f"Soundcard loopback device disappeared: {device.name}")


def _amplify_quiet_loopback(samples: np.ndarray) -> np.ndarray:
    """Boost very quiet loopback captures (some Realtek + soundcard setups)."""
    enabled = os.getenv("LOOPBACK_AUTO_GAIN", "1").strip().lower() not in ("0", "false", "no")
    if not enabled:
        return samples

    target_peak = float(os.getenv("LOOPBACK_GAIN_TARGET_PEAK", "8000")) / 32767.0
    max_gain = float(os.getenv("LOOPBACK_GAIN_MAX", "300"))
    min_peak = float(os.getenv("LOOPBACK_GAIN_MIN_PEAK", "500")) / 32767.0

    array = np.asarray(samples, dtype=np.float64)
    if array.size == 0:
        return samples

    peak = float(np.max(np.abs(array)))
    if peak >= min_peak or peak <= 1e-9:
        return samples

    gain = min(max_gain, target_peak / peak)
    return np.clip(array * gain, -1.0, 1.0)


def _float_samples_to_pcm16(samples: np.ndarray) -> bytes:
    array = np.asarray(samples)
    if array.ndim == 1:
        array = array[:, None]
    clipped = np.clip(array, -1.0, 1.0)
    return (clipped * 32767).astype("<i2").tobytes()


def _hostapi_name(hostapi_index: int) -> str:
    try:
        return str(sd.query_hostapis(hostapi_index).get("name", ""))
    except Exception:
        return ""


def _default_output_device(devices: list[AudioDevice]) -> AudioDevice | None:
    default = sd.default.device
    output_index = default[1] if isinstance(default, (list, tuple)) else None
    if output_index is None or output_index < 0:
        return None
    return next((device for device in devices if device.index == output_index), None)


def _is_wasapi(hostapi_name: str) -> bool:
    return "wasapi" in hostapi_name.lower()


def _mark_as_wasapi_loopback(device: AudioDevice) -> AudioDevice:
    return AudioDevice(
        index=device.index,
        name=device.name,
        hostapi=device.hostapi,
        max_input_channels=device.max_input_channels,
        max_output_channels=device.max_output_channels,
        default_samplerate=device.default_samplerate,
        kind="wasapi_output_loopback",
    )


def _extra_settings_for(device: AudioDevice):
    if device.kind == "wasapi_output_loopback":
        return sd.WasapiSettings(loopback=True)
    return None


def _supports_wasapi_loopback_setting() -> bool:
    try:
        return "loopback" in inspect.signature(sd.WasapiSettings).parameters
    except Exception:
        return False
