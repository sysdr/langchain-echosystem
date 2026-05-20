from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessageChunk, HumanMessage

from app.config import AGENT_DIR, settings
from app.runtime.base import AgentRuntime

_LOCAL_AGENT_ID = "local-deep-agent"
_threads: dict[str, list[dict[str, str]]] = {}


def _load_instructions() -> str:
    path = AGENT_DIR / "AGENTS.md"
    return path.read_text(encoding="utf-8") if path.exists() else "You are a helpful research assistant."


@lru_cache(maxsize=1)
def _get_agent():
    from deepagents import create_deep_agent
    from langgraph.checkpoint.memory import MemorySaver

    def web_search(query: str) -> str:
        """Search the web for information (local stub — set AGENT_RUNTIME=managed for real search)."""
        return (
            f"[Local mode] Web search is not connected. Query received: {query!r}. "
            "Configure Managed Deep Agents or LangSmith Deployment for live search."
        )

    return create_deep_agent(
        model=settings.default_model,
        tools=[web_search],
        system_prompt=_load_instructions(),
        checkpointer=MemorySaver(),
    )


class LocalRuntime(AgentRuntime):
    mode = "local"

    async def create_conversation(self) -> dict[str, str]:
        thread_id = str(uuid.uuid4())
        _threads[thread_id] = []
        return {"thread_id": thread_id, "agent_id": _LOCAL_AGENT_ID}

    async def stream_chat(
        self,
        thread_id: str,
        message: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        del user_timezone
        agent = _get_agent()
        history = _threads.setdefault(thread_id, [])
        history.append({"role": "user", "content": message.strip()})
        inputs = {
            "messages": [HumanMessage(content=message.strip())],
        }
        config = {"configurable": {"thread_id": thread_id}}

        async for chunk in agent.astream(
            inputs,
            config,
            stream_mode=["messages", "updates"],
        ):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk
            else:
                continue

            if mode == "messages":
                msg_chunk = data[0] if isinstance(data, tuple) else data
                if isinstance(msg_chunk, AIMessageChunk):
                    text = _content_text(msg_chunk.content)
                    if text:
                        yield "token", json.dumps({"text": text})
            elif mode == "updates":
                interrupt = _interrupt_from_updates(data)
                if interrupt:
                    yield "interrupt", json.dumps(interrupt)

        yield "done", "{}"

    async def stream_resume(
        self,
        thread_id: str,
        *,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        del user_timezone
        from langgraph.types import Command

        agent = _get_agent()
        config = {"configurable": {"thread_id": thread_id}}
        resume = {"decisions": [{"type": "approve"}]}
        async for chunk in agent.astream(
            Command(resume=resume),
            config,
            stream_mode=["messages", "updates"],
        ):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk
                if mode == "messages":
                    msg_chunk = data[0] if isinstance(data, tuple) else data
                    if hasattr(msg_chunk, "content"):
                        text = _content_text(msg_chunk.content)
                        if text:
                            yield "token", json.dumps({"text": text})
                elif mode == "updates":
                    interrupt = _interrupt_from_updates(data)
                    if interrupt:
                        yield "interrupt", json.dumps(interrupt)
        yield "done", "{}"

    async def resolve_interrupt(
        self,
        thread_id: str,
        *,
        approved: bool,
        agent_id: str | None = None,
    ) -> None:
        del thread_id, agent_id
        if not approved:
            return

    def health_extra(self) -> dict:
        return {"model": settings.default_model, "note": "Open-source deepagents (in-memory)"}


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _interrupt_from_updates(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    for value in data.values():
        if isinstance(value, dict) and "__interrupt__" in value:
            return _normalize_interrupt(value["__interrupt__"])
    if "__interrupt__" in data:
        return _normalize_interrupt(data["__interrupt__"])
    return None


def _normalize_interrupt(raw: Any) -> dict[str, Any]:
    items = raw if isinstance(raw, list) else [raw]
    first = items[0] if items else {}
    value = first.get("value", first) if isinstance(first, dict) else first
    tool = "unknown"
    if isinstance(value, dict):
        tool = value.get("tool_name") or value.get("name") or value.get("action", "tool")
    elif isinstance(value, str):
        tool = value
    return {
        "tool": str(tool),
        "description": str(value)[:500] if value else "Tool requires approval",
        "raw": first if isinstance(first, dict) else {"value": value},
    }
