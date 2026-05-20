from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.config import settings
from app.deepagents_client import (
    DeepAgentsClient,
    parse_interrupt_from_values,
    parse_messages_event,
)
from app.runtime.base import AgentRuntime


class ManagedRuntime(AgentRuntime):
    mode = "managed"

    def __init__(self) -> None:
        self._client = DeepAgentsClient()

    def _agent_id(self) -> str:
        if not settings.managed_agent_id:
            raise ValueError("MANAGED_AGENT_ID is required for managed runtime")
        return settings.managed_agent_id

    async def create_conversation(self) -> dict[str, str]:
        agent_id = self._agent_id()
        thread = await self._client.create_thread(agent_id)
        thread_id = (
            thread.get("thread_id")
            or thread.get("id")
            or (thread.get("thread") or {}).get("thread_id")
        )
        if not thread_id:
            raise ValueError("Unexpected thread response from Managed Deep Agents")
        return {"thread_id": str(thread_id), "agent_id": agent_id}

    async def stream_chat(
        self,
        thread_id: str,
        message: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        agent_id = self._agent_id()
        async for event_name, data in self._client.stream_run(
            thread_id,
            agent_id=agent_id,
            messages=[{"role": "user", "content": message.strip()}],
            stream_modes=["messages-tuple", "updates", "values"],
            user_timezone=user_timezone,
        ):
            if event_name == "messages":
                token = parse_messages_event(data)
                if token:
                    yield "token", json.dumps({"text": token})
            elif event_name == "values":
                interrupt = parse_interrupt_from_values(data)
                if interrupt:
                    yield "interrupt", json.dumps(interrupt)
                else:
                    yield "values", data
            else:
                yield event_name, data

    async def stream_resume(
        self,
        thread_id: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        agent_id = self._agent_id()
        async for event_name, data in self._client.stream_run(
            thread_id,
            agent_id=agent_id,
            messages=None,
            stream_modes=["messages-tuple", "updates", "values"],
            user_timezone=user_timezone,
        ):
            if event_name == "messages":
                token = parse_messages_event(data)
                if token:
                    yield "token", json.dumps({"text": token})
            elif event_name == "values":
                interrupt = parse_interrupt_from_values(data)
                if interrupt:
                    yield "interrupt", json.dumps(interrupt)
                else:
                    yield "values", data
            else:
                yield event_name, data

    async def resolve_interrupt(
        self,
        thread_id: str,
        *,
        approved: bool,
        agent_id: str | None = None,
    ) -> None:
        await self._client.resolve_interrupt(
            thread_id,
            agent_id=agent_id or self._agent_id(),
            approved=approved,
        )

    def health_extra(self) -> dict:
        return {
            "managed_agent_id": settings.managed_agent_id or None,
            "deepagents_base_url": settings.deepagents_base_url,
        }
