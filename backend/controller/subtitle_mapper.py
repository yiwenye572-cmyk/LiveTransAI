import sys
from pathlib import Path

from backend.translator.ast_client import ASTResponseEvent

PROTO_ROOT = Path(__file__).resolve().parents[1] / "translator" / "ast_protos"
if str(PROTO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROTO_ROOT))

from python_protogen.common.events_pb2 import Type  # noqa: E402


class SubtitleMapper:
    """Map Doubao AST events to frontend WebSocket JSON messages."""

    def __init__(self) -> None:
        self._sources: dict[int, str] = {}
        self._translations: dict[int, str] = {}
        self.sentence_count = 0

    def map_event(self, event: ASTResponseEvent) -> dict | None:
        sequence = event.sequence

        if event.event == Type.SourceSubtitleResponse:
            self._sources[sequence] = self._sources.get(sequence, "") + event.text
            return None

        if event.event == Type.SourceSubtitleEnd:
            if event.text:
                self._sources[sequence] = event.text
            return None

        if event.event == Type.TranslationSubtitleResponse:
            self._translations[sequence] = self._translations.get(sequence, "") + event.text
            return None

        if event.event == Type.TranslationSubtitleEnd:
            self.sentence_count += 1
            return {
                "type": "subtitle",
                "id": f"s_{sequence:03d}",
                "version": 1,
                "speaker": "speaker",
                "source": event.text or self._sources.get(sequence, ""),
                "translation": event.text or self._translations.get(sequence, ""),
                "confidence": "fast",
            }

        return None
