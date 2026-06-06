from dataclasses import dataclass, field
import time


@dataclass
class MemoryEntry:
    sentence_id: str
    source: str
    translation: str
    version: int
    correction_hints: list[str] = field(default_factory=list)
    recorded_at: float = field(default_factory=time.time)
