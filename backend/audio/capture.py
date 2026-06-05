import inspect
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sounddevice as sd


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


def list_audio_devices() -> list[AudioDevice]:
    devices = sd.query_devices()
    return [_device_from_raw(index, device, "device") for index, device in enumerate(devices)]


def find_loopback_device() -> AudioDevice:
    devices = list_audio_devices()

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
