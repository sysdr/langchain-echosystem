from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings
from app.deepagents_client import parse_messages_event
from app.runtime.base import AgentRuntime


class DeploymentRuntime(AgentRuntime):
    """LangSmith Deployment / Agent Server via langgraph-sdk."""

    mode = "deployment"

    def _client(self):
        from langgraph_sdk import get_client

        if not settings.langgraph_deployment_url:
            raise ValueError("LANGGRAPH_DEPLOYMENT_URL is required for deployment runtime")
        return get_client(
            url=settings.langgraph_deployment_url,
            api_key=settings.langsmith_api_key or None,
        )

    def _assistant_id(self) -> str:
        aid = settings.langgraph_assistant_id or settings.managed_agent_id
        if not aid:
            raise ValueError(
                "Set LANGGRAPH_ASSISTANT_ID (or MANAGED_AGENT_ID) for deployment runtime"
            )
        return aid

    async def create_conversation(self) -> dict[str, str]:
        client = self._client()
        thread = await client.threads.create()
        thread_id = thread.get("thread_id") or thread.get("id")
        if not thread_id:
            raise ValueError("Unexpected thread response from LangGraph deployment")
        return {"thread_id": str(thread_id), "agent_id": self._assistant_id()}

    async def stream_chat(
        self,
        thread_id: str,
        message: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        del user_timezone
        client = self._client()
        assistant_id = self._assistant_id()
        input_messages = [{"role": "user", "content": message.strip()}]

        async for chunk in client.runs.stream(
            thread_id,
            assistant_id,
            input={"messages": input_messages},
            stream_mode=["messages-tuple", "values"],
        ):
            event = getattr(chunk, "event", None) or chunk.get("event", "")
            data = getattr(chunk, "data", None) if hasattr(chunk, "data") else chunk.get("data")

            if event == "messages" or event == "messages-tuple":
                payload = json.dumps(data) if not isinstance(data, str) else data
                token = parse_messages_event(payload)
                if token:
                    yield "token", json.dumps({"text": token})
            elif event == "values":
                payload = json.dumps(data) if not isinstance(data, str) else data
                from app.deepagents_client import parse_interrupt_from_values

                interrupt = parse_interrupt_from_values(payload)
                if interrupt:
                    yield "interrupt", json.dumps(interrupt)
                else:
                    yield "values", payload

        yield "done", "{}"

    async def stream_resume(
        self,
        thread_id: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        del user_timezone
        client = self._client()
        assistant_id = self._assistant_id()
        async for chunk in client.runs.stream(
            thread_id,
            assistant_id,
            input=None,
            stream_mode=["messages-tuple", "values"],
        ):
            event = getattr(chunk, "event", None) or ""
            data = getattr(chunk, "data", None)
            if event in ("messages", "messages-tuple"):
                payload = json.dumps(data) if not isinstance(data, str) else data
                token = parse_messages_event(payload)
                if token:
                    yield "token", json.dumps({"text": token})
        yield "done", "{}"

    async def resolve_interrupt(
        self,
        thread_id: str,
        *,
        approved: bool,
        agent_id: str | None = None,
    ) -> None:
        del agent_id, approved
        return

    def health_extra(self) -> dict:
        return {
            "langgraph_deployment_url": settings.langgraph_deployment_url,
            "langgraph_assistant_id": settings.langgraph_assistant_id,
        }
