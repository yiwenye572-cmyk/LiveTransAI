import argparse
import asyncio
import sys
import threading
import time
import wave
from collections.abc import AsyncIterator

import numpy as np
import soundcard as sc

from backend.audio.capture import AudioCaptureError, LoopbackCapture, find_loopback_device, get_audio_device
from backend.config import ConfigError, load_ast_config
from backend.smoke_ast import configure_stdout, print_ast_event
from backend.translator.ast_client import ASTClient


async def timed_loopback_chunks(capture: LoopbackCapture, seconds: float) -> AsyncIterator[bytes]:
    deadline = time.monotonic() + seconds
    async for chunk in capture.chunks():
        yield chunk
        if time.monotonic() >= deadline:
            capture.stop()
            break


def play_sample_audio(seconds: float) -> None:
    speaker = sc.default_speaker()
    with wave.open("ast_python/test_audio.wav", "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        raw = wav_file.readframes(int(sample_rate * seconds))
        audio = (np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0)[:, None]

    with speaker.player(samplerate=sample_rate, channels=1) as player:
        player.play(audio)


async def run(seconds: float, device_index: int | None, play_sample: bool) -> None:
    config = load_ast_config()
    device = get_audio_device(device_index) if device_index is not None else find_loopback_device()
    client = ASTClient(config)

    print(f"Capturing from [{device.index}] {device.name} for {seconds:.1f}s...")
    if play_sample:
        print("Playing sample audio through default speaker.")
    else:
        print("Play audio on your computer now (YouTube, local file, etc.).")

    player_thread = None
    if play_sample:
        player_thread = threading.Thread(target=play_sample_audio, args=(seconds,), daemon=True)
        player_thread.start()
        await asyncio.sleep(0.5)

    async with LoopbackCapture(device=device) as capture:
        async for event in client.translate_stream(timed_loopback_chunks(capture, seconds)):
            print_ast_event(event)

    if player_thread:
        player_thread.join(timeout=seconds + 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream loopback audio to Doubao AST in real time.")
    parser.add_argument("--seconds", type=float, default=10.0, help="Capture duration in seconds.")
    parser.add_argument("--device-index", type=int, help="Override loopback device index.")
    parser.add_argument(
        "--play-sample",
        action="store_true",
        help="Play ast_python/test_audio.wav while capturing (for automated testing).",
    )
    return parser.parse_args()


def main() -> None:
    configure_stdout()
    args = parse_args()
    try:
        asyncio.run(run(args.seconds, args.device_index, args.play_sample))
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    except AudioCaptureError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
