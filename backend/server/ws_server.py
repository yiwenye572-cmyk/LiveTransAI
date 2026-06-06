import asyncio
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.audio.capture import (
    AudioCaptureError,
    AudioDevice,
    LoopbackCapture,
    find_loopback_device,
    get_audio_device,
    list_loopback_devices,
    list_output_speakers,
)
from backend.audio.tts_playback import TtsPlayback
from backend.bus.subtitle_bus import SubtitleBus
from backend.config import ConfigError, ast_config_for_session, load_ast_config, load_deepseek_config
from backend.controller.flow_controller import FlowController
from backend.controller.subtitle_mapper import SubtitleMapper
from backend.controller.tts_mapper import feed_tts_playback, map_tts_event
from backend.correction.engine import CorrectionEngine
from backend.glossary import GlossaryBundle, GlossaryError, GlossaryGenerator
from backend.persist.session_reader import SessionReader
from backend.persist.session_writer import SessionWriter
from backend.state.session_state import SessionPhase, SessionState
from backend.summary.updater import SummaryUpdater
from backend.translator.ast_client import ASTClient
from backend.translator.ast_corpus import AstCorpus
from backend.translator.languages import (
    build_languages_payload,
    source_language_label,
    target_language_label,
    validate_source_language,
)

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class GlossaryGenerateRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=300)


AUDIO_DEVICES_HINT = (
    "请在 Windows 设置 → 系统 → 声音 → 应用音量和设备偏好设置 中，"
    "将浏览器（网课）输出设为与「监听设备」相同的扬声器。"
)


def build_audio_devices_payload() -> dict:
    loopbacks = list_loopback_devices()
    outputs = list_output_speakers()
    default_loopback = find_loopback_device() if loopbacks else None
    return {
        "loopbacks": [
            {
                "index": device.index,
                "name": device.name,
                "id": device.id,
                "is_default": default_loopback is not None and device.index == default_loopback.index,
            }
            for device in loopbacks
        ],
        "outputs": [
            {"id": speaker.id, "name": speaker.name, "is_default": speaker.is_default}
            for speaker in outputs
        ],
        "hint": AUDIO_DEVICES_HINT,
    }


def resolve_audio_route(audio_config: dict | None) -> tuple[AudioDevice, str, str]:
    loopback = find_loopback_device()
    outputs = list_output_speakers()
    default_output = next((speaker for speaker in outputs if speaker.is_default), outputs[0] if outputs else None)

    loopback_index = audio_config.get("loopback_index") if audio_config else None
    if loopback_index is not None:
        loopback = get_audio_device(int(loopback_index))

    tts_output_id = (audio_config or {}).get("tts_output_id") or (default_output.id if default_output else "")
    if not tts_output_id:
        raise AudioCaptureError("No output speaker is available for TTS playback.")

    output_name = next((speaker.name for speaker in outputs if speaker.id == tts_output_id), tts_output_id)
    return loopback, tts_output_id, output_name


def apply_glossary_to_state(state: SessionState, bundle: GlossaryBundle | None) -> None:
    if bundle is None:
        return
    state.context_scenario = bundle.scenario
    state.context_instruction = bundle.instruction
    state.tone_hint = bundle.tone_hint
    state.static_glossary = dict(bundle.glossary_list)
    state.hot_words_list = list(bundle.hot_words_list)


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
        self._tts_player: TtsPlayback | None = None
        self._session_state: SessionState | None = None
        self._mapper: SubtitleMapper | None = None
        self._flow: FlowController | None = None
        self._persisted = False
        self._pending_glossary: GlossaryBundle | None = None
        self._audio_config: dict | None = None
        self._source_language: str | None = None
        self._backend_tts = False
        self._tts_enabled: bool | None = None

    def _build_pipeline(
        self,
        glossary: GlossaryBundle | None = None,
        source_language: str | None = None,
    ) -> FlowController:
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
        if source_language is not None:
            session_state.source_language = validate_source_language(source_language)
            session_state.target_language = "zh"
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
        if self.state_label in {"speaking", "paused"}:
            try:
                ast_config = load_ast_config()
                if ast_config.mode == "s2s":
                    await websocket.send_json(self._build_tts_config_payload(ast_config))
            except ConfigError:
                pass
        if self._session_state is not None and self.state_label in {"speaking", "paused", "finished"}:
            await websocket.send_json(self._build_session_sync())
            state = self._session_state
            if state.source_language:
                await websocket.send_json(
                    {
                        "type": "language_route",
                        "source": {
                            "code": state.source_language,
                            "label": source_language_label(state.source_language),
                        },
                        "target": {
                            "code": state.target_language,
                            "label": target_language_label(),
                        },
                    }
                )

    def _build_tts_config_payload(self, ast_config) -> dict:
        return {
            "type": "tts_config",
            "format": ast_config.target_audio_format,
            "rate": ast_config.target_audio_rate,
            "playback": "backend" if self._backend_tts else "browser",
        }

    async def handle_command(
        self,
        action: str,
        glossary: dict | None = None,
        audio_config: dict | None = None,
        tts_enabled: bool | None = None,
        source_language: str | None = None,
    ) -> None:
        if action == "start":
            await self.start(
                glossary,
                audio_config=audio_config,
                tts_enabled=tts_enabled,
                source_language=source_language,
            )
        elif action == "stop":
            await self.stop()
        elif action == "pause":
            await self.pause()
        elif action == "resume":
            await self.resume()
        elif action == "tts_enabled":
            if self._tts_player is not None and tts_enabled is not None:
                self._tts_player.set_enabled(bool(tts_enabled))

    def set_capture_suppress(self, suppress: bool) -> None:
        if self._backend_tts:
            return
        if self._capture is not None:
            self._capture.set_suppress_output(suppress)

    async def start(
        self,
        glossary: dict | None = None,
        audio_config: dict | None = None,
        tts_enabled: bool | None = None,
        source_language: str | None = None,
    ) -> None:
        if self._task and not self._task.done():
            return

        self._persisted = False
        self._audio_config = audio_config
        self._source_language = validate_source_language(source_language)
        self._tts_enabled = tts_enabled
        self.state_label = "speaking"
        self._mapper = SubtitleMapper()
        bundle = GlossaryBundle.from_client_payload(glossary) or self._pending_glossary
        self._flow = self._build_pipeline(bundle, source_language=self._source_language)
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
        try:
            ast_config = load_ast_config()
            self._backend_tts = ast_config.mode == "s2s" and ast_config.tts_playback == "backend"
            if ast_config.mode == "s2s":
                await self.manager.broadcast(self._build_tts_config_payload(ast_config))
        except ConfigError:
            self._backend_tts = False
        self._task = asyncio.create_task(self._run_pipeline(tts_enabled=tts_enabled))

    async def pause(self, reason: str = "user") -> None:
        if self.state_label != "speaking" or self._session_state is None:
            return
        self.state_label = "paused"
        self._session_state.phase = SessionPhase.PAUSED
        if self._capture is not None:
            self._capture.pause()
        logger.info("Translation session paused (%s)", reason)
        await self.manager.broadcast({"type": "status", "state": "paused", "reason": reason})

    async def resume(self) -> None:
        if self.state_label != "paused" or self._session_state is None:
            return
        self.state_label = "speaking"
        self._session_state.phase = SessionPhase.RUNNING

        pipeline_dead = self._task is None or self._task.done()
        if pipeline_dead:
            logger.info("Translation pipeline ended during pause; restarting")
            self._task = asyncio.create_task(self._run_pipeline(tts_enabled=self._tts_enabled))
            await self.manager.broadcast({"type": "status", "state": "speaking"})
            return

        if self._capture is not None:
            self._capture.resume()
        logger.info("Translation session resumed")
        await self.manager.broadcast({"type": "status", "state": "speaking"})

    async def stop(self) -> None:
        self.set_capture_suppress(False)
        if self._tts_player is not None:
            self._tts_player.stop()
            self._tts_player = None
        if self._capture is not None:
            self._capture.stop()
        if self._flow is not None:
            await self._flow.flush_pending()
            await self._flow.finalize_session()
        if self._session_state is not None:
            self._session_state.phase = SessionPhase.STOPPED
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

    def _build_ast_corpus(self) -> AstCorpus | None:
        state = self._session_state
        if state is None:
            return None
        if not state.hot_words_list and not state.static_glossary:
            return None
        return AstCorpus(
            hot_words=list(state.hot_words_list),
            glossary=dict(state.static_glossary),
        )

    async def _run_pipeline(self, tts_enabled: bool | None = None) -> None:
        flow = self._flow
        if flow is None:
            return
        try:
            config = load_ast_config()
        except ConfigError as exc:
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
            self.state_label = "ready"
            return

        source_language = validate_source_language(self._source_language or config.source_language)
        config = ast_config_for_session(config, source_language)
        if self._session_state is not None:
            self._session_state.source_language = source_language
            self._session_state.target_language = config.target_language

        backend_tts = config.mode == "s2s" and config.tts_playback == "backend"
        self._backend_tts = backend_tts

        client = ASTClient(config, corpus=self._build_ast_corpus())
        mapper = self._mapper
        assert mapper is not None

        tts_player: TtsPlayback | None = None
        loopback_device = find_loopback_device()
        tts_output_id = ""
        tts_output_name = ""

        try:
            loopback_device, tts_output_id, tts_output_name = resolve_audio_route(self._audio_config)
        except AudioCaptureError as exc:
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
            self.state_label = "ready"
            return

        if backend_tts:
            tts_player = TtsPlayback(
                speaker_id=tts_output_id,
                sample_rate=config.target_audio_rate,
                audio_format=config.target_audio_format,
            )
            if tts_enabled is not None:
                tts_player.set_enabled(bool(tts_enabled))
            tts_player.start()
            self._tts_player = tts_player

        await self.manager.broadcast(
            {
                "type": "audio_route",
                "capture": {"index": loopback_device.index, "name": loopback_device.name},
                "tts_output": {"id": tts_output_id, "name": tts_output_name},
                "playback": "backend" if backend_tts else "browser",
            }
        )
        await self.manager.broadcast(
            {
                "type": "language_route",
                "source": {
                    "code": source_language,
                    "label": source_language_label(source_language),
                },
                "target": {"code": config.target_language, "label": target_language_label()},
            }
        )

        try:
            async with LoopbackCapture(device=loopback_device) as capture:
                self._capture = capture
                async for event in client.translate_stream(capture.chunks()):
                    subtitle = mapper.map_event(event)
                    if subtitle is not None:
                        await flow.on_new_sentence(subtitle)

                    if backend_tts and tts_player is not None:
                        feed_tts_playback(tts_player, event, config)
                        tts_message = map_tts_event(event, config)
                        if tts_message is not None and tts_message["type"] != "tts_audio":
                            await self.manager.broadcast(tts_message)
                    else:
                        tts_message = map_tts_event(event, config)
                        if tts_message is not None:
                            await self.manager.broadcast(tts_message)
        except AudioCaptureError as exc:
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
        except Exception as exc:
            logger.exception("Translation pipeline failed: %s", exc)
            await self.manager.broadcast({"type": "status", "state": "error", "message": str(exc)})
        finally:
            self._capture = None
            if tts_player is not None:
                tts_player.stop()
                self._tts_player = None
            if flow is not None:
                await flow.flush_pending()
                if self.state_label != "paused":
                    await flow.finalize_session()
                    self._maybe_persist_session()
            if self.state_label == "speaking":
                self.state_label = "finished"
                await self.manager.broadcast({"type": "status", "state": "finished"})
            elif self.state_label == "paused":
                logger.warning("Translation pipeline ended while paused; resume will restart if possible")
                await self.manager.broadcast(
                    {
                        "type": "status",
                        "state": "paused",
                        "reason": "pipeline_lost",
                        "message": "AST 连接已断开，点击恢复将重新连接",
                    }
                )

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

    @app.get("/api/languages")
    async def list_languages_api() -> dict:
        try:
            base = load_ast_config()
            default_source = base.source_language
        except ConfigError:
            default_source = "en"
        return build_languages_payload(default_source=default_source)

    @app.get("/api/audio/devices")
    async def list_audio_devices_api() -> dict:
        return build_audio_devices_payload()

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
                if action in {"start", "stop", "pause", "resume"}:
                    glossary = payload.get("glossary") if action == "start" else None
                    audio_config = payload.get("audio") if action == "start" else None
                    tts_enabled = payload.get("tts_enabled") if action == "start" else None
                    source_language = payload.get("source_language") if action == "start" else None
                    await session.handle_command(
                        action,
                        glossary=glossary,
                        audio_config=audio_config,
                        tts_enabled=tts_enabled,
                        source_language=source_language,
                    )
                elif action == "tts_enabled":
                    await session.handle_command(
                        "tts_enabled",
                        tts_enabled=bool(payload.get("enabled", True)),
                    )
                elif action == "suppress_capture":
                    session.set_capture_suppress(bool(payload.get("suppress", True)))
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            if not manager.connections and session.state_label == "ready":
                await session.stop()

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app
