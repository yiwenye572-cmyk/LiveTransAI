import asyncio
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import websockets

from backend.config import ASTConfig


PROTO_ROOT = Path(__file__).resolve().parent / "ast_protos"
if str(PROTO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROTO_ROOT))

from python_protogen.common.events_pb2 import Type  # noqa: E402
from python_protogen.products.understanding.ast.ast_service_pb2 import (  # noqa: E402
    TranslateRequest,
    TranslateResponse,
)


@dataclass(frozen=True)
class ASTResponseEvent:
    event: int
    event_name: str
    sequence: int
    text: str
    start_time: int
    end_time: int
    speaker_changed: bool
    message: str
    data_length: int


class ASTClient:
    """Minimal Doubao AST WebSocket client used by the first smoke test."""

    def __init__(self, config: ASTConfig):
        self.config = config

    async def translate_file(self, audio_path: Path | str) -> AsyncIterator[ASTResponseEvent]:
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        session_id = str(uuid.uuid4())
        async with await self._connect() as ws:
            await self._send_start_session(ws, session_id)
            started = await self._receive(ws)
            yield started
            if started.event != Type.SessionStarted:
                raise RuntimeError(f"AST session did not start: {started.event_name} {started.message}")

            sender = asyncio.create_task(self._send_audio_file(ws, session_id, audio_file))
            try:
                while True:
                    event = await self._receive(ws)
                    yield event
                    if event.event in (Type.SessionFinished, Type.SessionFailed, Type.SessionCanceled):
                        break
            finally:
                await sender

    async def _connect(self):
        headers = {
            "X-Api-Key": self.config.api_key,
            "X-Api-Resource-Id": self.config.resource_id,
        }

        try:
            return await websockets.connect(
                self.config.ws_url,
                additional_headers=headers,
                max_size=1000000000,
                ping_interval=None,
            )
        except TypeError:
            return await websockets.connect(
                self.config.ws_url,
                extra_headers=headers,
                max_size=1000000000,
                ping_interval=None,
            )

    async def _send_start_session(self, ws, session_id: str) -> None:
        request = self._base_request(session_id, Type.StartSession)
        request.request.mode = self.config.mode
        request.request.source_language = self.config.source_language
        request.request.target_language = self.config.target_language
        await self._send_request(ws, request)

    async def _send_audio_file(self, ws, session_id: str, audio_file: Path) -> None:
        with audio_file.open("rb") as file:
            while chunk := file.read(self.config.chunk_size_bytes):
                request = self._base_request(session_id, Type.TaskRequest)
                request.source_audio.binary_data = chunk
                await self._send_request(ws, request)
                await asyncio.sleep(self.config.chunk_ms / 1000)

        await self._send_request(ws, self._base_request(session_id, Type.FinishSession))

    def _base_request(self, session_id: str, event: int) -> TranslateRequest:
        request = TranslateRequest()
        request.request_meta.SessionID = session_id
        request.event = event
        request.user.uid = "livetransai"
        request.user.did = "livetransai-local"
        request.user.platform = "Windows"
        request.source_audio.format = "wav"
        request.source_audio.codec = "raw"
        request.source_audio.rate = self.config.sample_rate
        request.source_audio.bits = self.config.sample_bits
        request.source_audio.channel = self.config.channels

        if self.config.mode == "s2s":
            request.target_audio.format = "ogg_opus"
            request.target_audio.rate = 24000

        return request

    async def _send_request(self, ws, request: TranslateRequest) -> None:
        await ws.send(request.SerializeToString())

    async def _receive(self, ws) -> ASTResponseEvent:
        raw = await ws.recv()
        response = TranslateResponse()
        response.ParseFromString(raw)

        return ASTResponseEvent(
            event=response.event,
            event_name=self._event_name(response.event),
            sequence=response.response_meta.Sequence,
            text=response.text,
            start_time=response.start_time,
            end_time=response.end_time,
            speaker_changed=response.spk_chg,
            message=response.response_meta.Message,
            data_length=len(response.data),
        )

    @staticmethod
    def _event_name(event: int) -> str:
        try:
            return Type.Name(event)
        except ValueError:
            return f"Unknown({event})"
