from backend.memory.memory_entry import MemoryEntry

__all__ = ["MemoryEntry", "MemoryStore"]


def __getattr__(name: str):
    if name == "MemoryStore":
        from backend.memory.memory_store import MemoryStore

        return MemoryStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
