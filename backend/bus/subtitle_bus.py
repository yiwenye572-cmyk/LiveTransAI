import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable


EventHandler = Callable[[dict], Awaitable[None]]


class SubtitleBus:
    """Simple pub/sub bus for subtitle pipeline modules."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, data: dict) -> None:
        for handler in self._handlers[event_type]:
            await handler(data)

    def publish_fire_and_forget(self, event_type: str, data: dict) -> None:
        for handler in self._handlers[event_type]:
            asyncio.create_task(handler(data))
