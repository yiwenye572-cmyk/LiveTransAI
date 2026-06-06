from backend.format.formatted_document import FormatSlot, FormattedDocument

__all__ = ["FormatSlot", "FormattedDocument", "TextFormatter"]


def __getattr__(name: str):
    if name == "TextFormatter":
        from backend.format.text_formatter import TextFormatter

        return TextFormatter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
