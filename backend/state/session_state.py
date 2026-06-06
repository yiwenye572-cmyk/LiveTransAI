from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from backend.format.formatted_document import FormattedDocument
from backend.memory.memory_entry import MemoryEntry
from backend.summary.running_summary import RunningSummary


class SessionPhase(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class SessionState:
    session_id: str = ""
    started_at: float = 0.0
    stopped_at: float = 0.0
    session_dir: Path | None = None
    phase: SessionPhase = SessionPhase.RUNNING
    sentence_count: int = 0
    correction_count: int = 0
    ast_fragment_count: int = 0
    merge_count: int = 0
    displayed_sentences: list[dict] = field(default_factory=list)
    running_summary: RunningSummary = field(default_factory=RunningSummary)
    formatted_doc: FormattedDocument = field(default_factory=FormattedDocument)
    memory_entries: list[MemoryEntry] = field(default_factory=list)
