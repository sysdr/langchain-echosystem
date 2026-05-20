from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class AgentRuntime(ABC):
    mode: str

    @abstractmethod
    async def create_conversation(self) -> dict[str, str]:
        """Return {thread_id, agent_id}."""

    @abstractmethod
    async def stream_chat(
        self,
        thread_id: str,
        message: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield (sse_event_name, data_json_string)."""

    async def stream_resume(
        self,
        thread_id: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        async for event in self.stream_chat(thread_id, "", user_timezone=user_timezone):
            if event[0] != "done" or event[1] != "{}":
                yield event

    @abstractmethod
    async def resolve_interrupt(
        self,
        thread_id: str,
        *,
        approved: bool,
        agent_id: str | None = None,
    ) -> None:
        pass

    @abstractmethod
    def health_extra(self) -> dict[str, Any]:
        pass
