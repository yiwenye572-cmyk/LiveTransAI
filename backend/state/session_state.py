from dataclasses import dataclass, field
from enum import Enum

from backend.summary.running_summary import RunningSummary


class SessionPhase(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class SessionState:
    phase: SessionPhase = SessionPhase.RUNNING
    sentence_count: int = 0
    correction_count: int = 0
    displayed_sentences: list[dict] = field(default_factory=list)
    running_summary: RunningSummary = field(default_factory=RunningSummary)
