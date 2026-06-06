import asyncio
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.audio.capture import AudioCaptureError, LoopbackCapture
from backend.bus.subtitle_bus import SubtitleBus
from backend.config import ConfigError, load_ast_config, load_deepseek_config
from backend.controller.flow_controller import FlowController
from backend.controller.subtitle_mapper import SubtitleMapper
from backend.correction.engine import CorrectionEngine
from backend.glossary import GlossaryBundle, GlossaryError, GlossaryGenerator
from backend.persist.session_reader import SessionReader
from backend.persist.session_writer import SessionWriter
from backend.state.session_state import SessionPhase, SessionState
from backend.summary.updater import SummaryUpdater
from backend.translator.ast_client import ASTClient

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class GlossaryGenerateRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=300)


def apply_glossary_to_state(state: SessionState, bundle: GlossaryBundle | None) -> None:
    if bundle is None:
        return
    state.context_scenario = bundle.scenario
    state.context_instruction = bundle.instruction
    state.tone_hint = bundle.tone_hint
    state.static_glossary = dict(bundle.glossary_list)


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
        self.state_label = "ready"
        self._task: asyncio.Task | None = None
        self._capture: LoopbackCapture | None = None
        self._session_state: SessionState | None = None
        self._mapper: SubtitleMapper | None = None
        self._flow: FlowController | None = None
        self._persisted = False
        self._pending_glossary: GlossaryBundle | None = None

    def _build_pipeline(self, glossary: GlossaryBundle | None = None) -> FlowController:
        session_id = str(uuid.uuid4())
        started_at = time.time()
        session_dir = SessionWriter.ensure_session_dir(session_id, started_at=started_at)
        session_state = SessionState(
            phase=SessionPhase.RUNNING,
            session_id=session_id,
            started_at=started_at,
            session_dir=session_dir,
        )
        apply_glossary_to_state(session_state, glossary)
        bus = SubtitleBus()
        correction_engine = CorrectionEngine(load_deepseek_config())
        summary_updater = SummaryUpdater(load_deepseek_config())
        flow = FlowController(session_state, bus, correction_engine, summary_updater)

        bus.subscribe("commit_display", self._on_commit_display)
        bus.subscribe("correction", self._on_correction)
        bus.subscribe("summary_update", self._on_summary_update)
        bus.subscribe("formatted_delta", self._on_formatted_delta)
        bus.subscribe("formatted_patch", self._on_formatted_patch)
        bus.subscribe("formatted_snapshot", self._on_formatted_snapshot)

        self._session_state = session_state
        return flow

    async def _on_commit_display(self, payload: dict) -> None:
        await self.manager.broadcast(payload)
        await self._broadcast_metrics()

    async def _on_correction(self, payload: dict) -> None:
        await self.manager.broadcast(payload)
        await self._broadcast_metrics()

    async def _on_summary_update(self, payload: dict) -> None:
        await self.manager.broadcast(payload)

    async def _on_formatted_delta(self, payload: dict) -> None:
        await self.manager.broadcast(payload)

    async def _on_formatted_patch(self, payload: dict) -> None:
        await self.manager.broadcast(payload)

    async def _on_formatted_snapshot(self, payload: dict) -> None:
        await self.manager.broadcast(payload)

    async def _broadcast_metrics(self) -> None:
        if self._session_state is None:
            return
        await self.manager.broadcast(self._build_metrics_payload())

    def _build_metrics_payload(self) -> dict:
        assert self._session_state is not None
        return {
            "type": "metrics",
            "sentence_count": self._session_state.sentence_count,
            "correction_count": self._session_state.correction_count,
            "merge_count": self._session_state.merge_count,
            "ast_fragment_count": self._session_state.ast_fragment_count,
            "memory_count": len(self._session_state.memory_entries),
            "latency_p50": 0,
            "latency_p99": 0,
            "cost_estimate": 0,
        }

    def _build_session_sync(self) -> dict:
        state = self._session_state
        if state is None:
            return {"type": "session_sync", "status": self.state_label}

        subtitles = []
        for item in state.displayed_sentences:
            version = int(item.get("version", 1))
            subtitles.append(
                {
                    "type": "subtitle",
                    "id": item.get("id", ""),
                    "version": version,
                    "source": item.get("source", ""),
                    "translation": item.get("translation", ""),
                    "confidence": "corrected" if version > 1 else "fast",
                }
            )

        return {
            "type": "session_sync",
            "status": self.state_label,
            "subtitles": subtitles,
            "summary": state.running_summary.to_ws_payload(
                sentence_count=state.sentence_count
            ),
            "formatted": {
                "paragraphs": state.formatted_doc.build_snapshot(),
                "updated_at_sentence": state.sentence_count,
            },
            "metrics": {
                key: value
                for key, value in self._build_metrics_payload().items()
                if key != "type"
            },
        }

    async def send_initial_state(self, websocket: WebSocket) -> None:
        await websocket.send_json({"type": "status", "state": self.state_label})
        if self._session_state is not None and self.state_label in {"speaking", "finished"}:
            await websocket.send_json(self._build_session_sync())

    async def handle_command(self, action: str, glossary: dict | None = None) -> None:
        if action == "start":
            await self.start(glossary)
        elif action == "stop":
            await self.stop()

    async def start(self, glossary: dict | None = None) -> None:
        if self._task and not self._task.done():
            return

        self._persisted = False
        self.state_label = "speaking"
        self._mapper = SubtitleMapper()
        bundle = GlossaryBundle.from_client_payload(glossary) or self._pending_glossary
        self._flow = self._build_pipeline(bundle)
        await self.manager.broadcast({"type": "status", "state": "speaking"})
        await self.manager.broadcast(
            {
                "type": "summary",
                "topic": "",
                "term_map": {},
                "bullet_points": [],
                "updated_at_sentence": 0,
            }
        )
        await self.manager.broadcast(
            {
                "type": "formatted_snapshot",
                "paragraphs": [],
                "updated_at_sentence": 0,
            }
        )
        self._task = asyncio.create_task(self._run_pipeline())

    async def stop(self) -> None:
        if self._capture is not None:
            self._capture.stop()
        if self._flow is not None:
            await self._flow.flush_pending()
            await self._flow.finalize_session()
        self._maybe_persist_session()
        if self._task is not None:
            try:
                await self._task
            except Exception as exc:
                logger.exception("Translation session stopped with error: %s", exc)
            finally:
                self._task = None

        self.state_label = "ready"
        self._session_state = None
        self._mapper = None
        self._flow = None
        await self.manager.broadcast({"type": "status", "state": "ready"})

    async def _run_pipeline(self) -> None:
        flow = self._flow
        if flow is None:
            return
        try:
            config = load_ast_config()
        except ConfigError as exc:
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
            self.state_label = "ready"
            return

        client = ASTClient(config)
        mapper = self._mapper
        assert mapper is not None

        try:
            async with LoopbackCapture() as capture:
                self._capture = capture
                async for event in client.translate_stream(capture.chunks()):
                    subtitle = mapper.map_event(event)
                    if subtitle is not None:
                        await flow.on_new_sentence(subtitle)
        except AudioCaptureError as exc:
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
        except Exception as exc:
            logger.exception("Translation pipeline failed: %s", exc)
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
        finally:
            self._capture = None
            if flow is not None:
                await flow.flush_pending()
                await flow.finalize_session()
            self._maybe_persist_session()
            if self.state_label == "speaking":
                self.state_label = "finished"
                await self.manager.broadcast({"type": "status", "state": "finished"})

    def _maybe_persist_session(self) -> None:
        if self._persisted or self._session_state is None:
            return
        if not self._session_state.session_id:
            return
        SessionWriter.write_session_state(self._session_state)
        self._persisted = True


def create_app() -> FastAPI:
    app = FastAPI(title="LiveTransAI")
    manager = ConnectionManager()
    session = TranslationSession(manager)

    @app.post("/api/glossary/generate")
    async def generate_glossary(body: GlossaryGenerateRequest) -> dict:
        generator = GlossaryGenerator(load_deepseek_config())
        try:
            bundle = await generator.generate(body.scenario, body.instruction)
        except GlossaryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        session._pending_glossary = bundle
        return bundle.to_api_dict()

    @app.post("/api/session/stop")
    async def stop_session() -> dict:
        await session.stop()
        return {"ok": True}

    @app.get("/api/sessions")
    async def list_sessions() -> dict:
        return {"sessions": SessionReader.list_sessions()}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict:
        detail = SessionReader.get_session(session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return detail

    @app.websocket("/stream")
    async def stream(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        await session.send_initial_state(websocket)
        try:
            while True:
                payload = await websocket.receive_json()
                if payload.get("type") != "command":
                    continue
                action = payload.get("action")
                if action in {"start", "stop"}:
                    glossary = payload.get("glossary") if action == "start" else None
                    await session.handle_command(action, glossary=glossary)
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            if not manager.connections and session.state_label == "ready":
                await session.stop()

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app
