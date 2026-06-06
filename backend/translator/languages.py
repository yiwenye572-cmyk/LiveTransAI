from dataclasses import dataclass

DEFAULT_SOURCE_LANGUAGE = "en"
TARGET_LANGUAGE = "zh"
TARGET_LANGUAGE_LABEL = "中文"


@dataclass(frozen=True)
class LanguageOption:
    code: str
    label: str


SUPPORTED_SOURCE_LANGUAGES: tuple[LanguageOption, ...] = (
    LanguageOption("en", "英语"),
    LanguageOption("ja", "日语"),
    LanguageOption("pt", "葡萄牙语"),
    LanguageOption("es", "西班牙语"),
    LanguageOption("id", "印尼语"),
    LanguageOption("de", "德语"),
    LanguageOption("fr", "法语"),
)

_SOURCE_BY_CODE = {item.code: item for item in SUPPORTED_SOURCE_LANGUAGES}


def list_source_languages() -> list[dict[str, str]]:
    return [{"code": item.code, "label": item.label} for item in SUPPORTED_SOURCE_LANGUAGES]


def validate_source_language(code: str | None) -> str:
    normalized = (code or "").strip().lower()
    if normalized in _SOURCE_BY_CODE:
        return normalized
    return DEFAULT_SOURCE_LANGUAGE


def source_language_label(code: str) -> str:
    item = _SOURCE_BY_CODE.get(code)
    return item.label if item else code


def target_language_label() -> str:
    return TARGET_LANGUAGE_LABEL


def build_languages_payload(default_source: str | None = None) -> dict:
    resolved_default = validate_source_language(default_source or DEFAULT_SOURCE_LANGUAGE)
    return {
        "sources": list_source_languages(),
        "target": {"code": TARGET_LANGUAGE, "label": TARGET_LANGUAGE_LABEL},
        "default_source": resolved_default,
    }
