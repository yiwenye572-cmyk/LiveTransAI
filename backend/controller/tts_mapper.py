import base64
import sys
from pathlib import Path

from backend.config import ASTConfig
from backend.translator.ast_client import ASTResponseEvent

PROTO_ROOT = Path(__file__).resolve().parents[1] / "translator" / "ast_protos"
if str(PROTO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROTO_ROOT))

from python_protogen.common.events_pb2 import Type  # noqa: E402


def feed_tts_playback(player, event: ASTResponseEvent, config: ASTConfig) -> None:
    if config.mode != "s2s":
        return

    if event.event == Type.TTSSentenceStart:
        player.on_tts_start(event.sequence)
        return

    if event.event == Type.TTSResponse:
        player.on_tts_audio(event.sequence, event.audio_data)
        return

    if event.event == Type.TTSSentenceEnd:
        player.on_tts_end(event.sequence)


def map_tts_event(event: ASTResponseEvent, config: ASTConfig) -> dict | None:
    if config.mode != "s2s":
        return None

    if event.event == Type.TTSSentenceStart:
        return {
            "type": "tts_start",
            "sequence": event.sequence,
            "start_time": event.start_time,
            "end_time": event.end_time,
        }

    if event.event == Type.TTSResponse:
        if not event.audio_data:
            return None
        return {
            "type": "tts_audio",
            "sequence": event.sequence,
            "format": config.target_audio_format,
            "rate": config.target_audio_rate,
            "data": base64.b64encode(event.audio_data).decode("ascii"),
        }

    if event.event == Type.TTSSentenceEnd:
        return {
            "type": "tts_end",
            "sequence": event.sequence,
            "start_time": event.start_time,
            "end_time": event.end_time,
        }

    return None
