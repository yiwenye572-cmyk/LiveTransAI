import argparse
import asyncio
import sys
from pathlib import Path

from backend.config import ConfigError, load_ast_config
from backend.translator.ast_client import ASTClient


TEXT_EVENTS = {
    "SourceSubtitleStart",
    "SourceSubtitleResponse",
    "SourceSubtitleEnd",
    "TranslationSubtitleStart",
    "TranslationSubtitleResponse",
    "TranslationSubtitleEnd",
}


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def run(audio_path: Path) -> None:
    config = load_ast_config()
    client = ASTClient(config)

    async for event in client.translate_file(audio_path):
        if event.event_name in TEXT_EVENTS:
            print(
                f"[{event.event_name}] seq={event.sequence} "
                f"time={event.start_time}-{event.end_time} text={event.text}"
            )
        else:
            detail = f" message={event.message}" if event.message else ""
            print(f"[{event.event_name}] seq={event.sequence}{detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal Doubao AST smoke test.")
    parser.add_argument(
        "--audio",
        type=Path,
        default=Path("ast_python/test_audio.wav"),
        help="Path to a 16kHz, 16-bit, mono wav file.",
    )
    return parser.parse_args()


def main() -> None:
    configure_stdout()
    args = parse_args()
    try:
        asyncio.run(run(args.audio))
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
