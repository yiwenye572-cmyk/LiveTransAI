import argparse
from pathlib import Path

from backend.audio.capture import (
    AudioCaptureError,
    find_loopback_device,
    get_audio_device,
    list_audio_devices,
    record_wav,
    wav_stats,
)
from backend.smoke_ast import configure_stdout


def print_devices() -> None:
    devices = list_audio_devices()
    selected = find_loopback_device()

    print("Audio devices:")
    for device in devices:
        marker = " <- selected" if device.index == selected.index else ""
        print(
            f"[{device.index}] {device.name} | hostapi={device.hostapi} "
            f"| in={device.max_input_channels} out={device.max_output_channels} "
            f"| rate={device.default_samplerate:.0f}{marker}"
        )
    print(f"\nSelected capture device: [{selected.index}] {selected.name} ({selected.kind})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List or test local audio capture devices.")
    parser.add_argument("--list", action="store_true", help="List audio devices and selected capture device.")
    parser.add_argument("--record", action="store_true", help="Record a short wav file from loopback/microphone.")
    parser.add_argument("--device-index", type=int, help="Override the selected capture device index.")
    parser.add_argument("--seconds", type=float, default=5.0, help="Recording duration in seconds.")
    parser.add_argument("--out", type=Path, default=Path("tmp/loopback_test.wav"), help="Output wav path.")
    return parser.parse_args()


def main() -> None:
    configure_stdout()
    args = parse_args()

    try:
        if args.list or not args.record:
            print_devices()

        if args.record:
            selected = get_audio_device(args.device_index) if args.device_index is not None else find_loopback_device()
            print(f"Recording {args.seconds:.1f}s from [{selected.index}] {selected.name}...")
            output = record_wav(args.out, args.seconds, device=selected)
            print(f"Saved test audio: {output}")
            stats = wav_stats(output)
            print(
                f"Audio stats: frames={stats.frames} rate={stats.sample_rate} "
                f"channels={stats.channels} rms={stats.rms:.2f} peak={stats.peak}"
            )
            if stats.peak == 0:
                print("Warning: captured audio is silent. Check system mute, output device, and active playback.")
    except AudioCaptureError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
