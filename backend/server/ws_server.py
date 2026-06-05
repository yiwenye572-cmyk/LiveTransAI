import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.audio.capture import AudioCaptureError, LoopbackCapture
from backend.config import ConfigError, load_ast_config
from backend.controller.subtitle_mapper import SubtitleMapper
from backend.translator.ast_client import ASTClient

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        stale: list[WebSocket] = []
        for websocket in self.connections:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)


class TranslationSession:
    def __init__(self, manager: ConnectionManager) -> None:
        self.manager = manager
        self.state = "ready"
        self._task: asyncio.Task | None = None
        self._capture: LoopbackCapture | None = None
        self._mapper = SubtitleMapper()

    async def handle_command(self, action: str) -> None:
        if action == "start":
            await self.start()
        elif action == "stop":
            await self.stop()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        self.state = "speaking"
        self._mapper = SubtitleMapper()
        await self.manager.broadcast({"type": "status", "state": "speaking"})
        self._task = asyncio.create_task(self._run_pipeline())

    async def stop(self) -> None:
        if self._capture is not None:
            self._capture.stop()
        if self._task is not None:
            try:
                await self._task
            except Exception as exc:
                logger.exception("Translation session stopped with error: %s", exc)
            finally:
                self._task = None

        self.state = "ready"
        await self.manager.broadcast({"type": "status", "state": "ready"})

    async def _run_pipeline(self) -> None:
        try:
            config = load_ast_config()
        except ConfigError as exc:
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
            self.state = "ready"
            return

        client = ASTClient(config)
        try:
            async with LoopbackCapture() as capture:
                self._capture = capture
                async for event in client.translate_stream(capture.chunks()):
                    subtitle = self._mapper.map_event(event)
                    if subtitle is not None:
                        await self.manager.broadcast(subtitle)
                        await self.manager.broadcast(
                            {
                                "type": "metrics",
                                "sentence_count": self._mapper.sentence_count,
                                "correction_count": 0,
                                "latency_p50": 0,
                                "latency_p99": 0,
                                "cost_estimate": 0,
                            }
                        )
        except AudioCaptureError as exc:
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
        except Exception as exc:
            logger.exception("Translation pipeline failed: %s", exc)
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
        finally:
            self._capture = None
            if self.state == "speaking":
                self.state = "finished"
                await self.manager.broadcast({"type": "status", "state": "finished"})


def create_app() -> FastAPI:
    app = FastAPI(title="LiveTransAI")
    manager = ConnectionManager()
    session = TranslationSession(manager)

    @app.websocket("/stream")
    async def stream(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        await websocket.send_json({"type": "status", "state": session.state})
        try:
            while True:
                payload = await websocket.receive_json()
                if payload.get("type") != "command":
                    continue
                action = payload.get("action")
                if action in {"start", "stop"}:
                    await session.handle_command(action)
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            if not manager.connections:
                await session.stop()

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app
