import os
from dataclasses import dataclass, replace

from dotenv import load_dotenv

from backend.translator.languages import TARGET_LANGUAGE, validate_source_language


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing."""


@dataclass(frozen=True)
class ASTConfig:
    api_key: str
    resource_id: str = "volc.service_type.10053"
    ws_url: str = "wss://openspeech.bytedance.com/api/v4/ast/v2/translate"
    mode: str = "s2s"
    source_language: str = "en"
    target_language: str = "zh"
    speaker_id: str = ""
    target_audio_format: str = "pcm"
    target_audio_rate: int = 24000
    tts_playback: str = "backend"
    sample_rate: int = 16000
    sample_bits: int = 16
    channels: int = 1
    chunk_ms: int = 80

    @property
    def chunk_size_bytes(self) -> int:
        bytes_per_sample = self.sample_bits // 8
        return int(self.sample_rate * self.chunk_ms / 1000) * bytes_per_sample * self.channels


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout_sec: float = 45.0


def load_ast_config() -> ASTConfig:
    load_dotenv()

    api_key = os.getenv("DOUBAO_API_KEY", "").strip()
    if not api_key or api_key == "your-api-key":
        raise ConfigError("Missing DOUBAO_API_KEY. Copy .env.example to .env and fill your API key.")

    return ASTConfig(
        api_key=api_key,
        resource_id=os.getenv("DOUBAO_RESOURCE_ID", ASTConfig.resource_id).strip(),
        ws_url=os.getenv("DOUBAO_AST_WS_URL", ASTConfig.ws_url).strip(),
        mode=os.getenv("AST_MODE", ASTConfig.mode).strip(),
        source_language=os.getenv("SOURCE_LANGUAGE", ASTConfig.source_language).strip(),
        target_language=os.getenv("TARGET_LANGUAGE", ASTConfig.target_language).strip(),
        speaker_id=os.getenv("AST_SPEAKER_ID", ASTConfig.speaker_id).strip(),
        target_audio_format=os.getenv("AST_TARGET_AUDIO_FORMAT", ASTConfig.target_audio_format).strip(),
        target_audio_rate=int(os.getenv("AST_TARGET_AUDIO_RATE", str(ASTConfig.target_audio_rate))),
        tts_playback=os.getenv("TTS_PLAYBACK", ASTConfig.tts_playback).strip().lower(),
    )


def ast_config_for_session(base: ASTConfig, source_language: str | None) -> ASTConfig:
    return replace(
        base,
        source_language=validate_source_language(source_language or base.source_language),
        target_language=TARGET_LANGUAGE,
    )


def load_deepseek_config() -> DeepSeekConfig | None:
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key == "your-deepseek-api-key":
        return None

    return DeepSeekConfig(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", DeepSeekConfig.base_url).strip(),
        model=os.getenv("DEEPSEEK_MODEL", DeepSeekConfig.model).strip(),
    )
