"""HTTP client for the LangSmith Managed Deep Agents API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings


class DeepAgentsError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class DeepAgentsClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.langsmith_api_key
        self.base_url = base_url or settings.deepagents_base_url
        if not self.api_key:
            raise DeepAgentsError(
                401,
                "LANGSMITH_API_KEY is required. Set it in .env or the environment.",
            )

    def _headers(self, accept: str | None = None) -> dict[str, str]:
        headers = {"X-Api-Key": self.api_key, "Content-Type": "application/json"}
        if accept:
            headers["Accept"] = accept
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        accept: str | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(accept),
                json=json_body,
            )
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise DeepAgentsError(response.status_code, str(detail))
        if response.status_code == 204:
            return None
        return response.json()

    async def list_agents(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/agents")
        if isinstance(data, list):
            return data
        return data.get("agents", data.get("items", []))

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/agents/{agent_id}")

    async def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/agents", json_body=payload)

    async def update_agent(
        self, agent_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request("PATCH", f"/agents/{agent_id}", json_body=payload)

    async def delete_agent(self, agent_id: str) -> None:
        await self._request("DELETE", f"/agents/{agent_id}")

    async def create_thread(
        self,
        agent_id: str,
        *,
        test_run: bool = False,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/threads",
            json_body={
                "agent_id": agent_id,
                "options": {
                    "test_run": test_run,
                    "skip_memory_write_protection": False,
                },
            },
        )

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/threads/{thread_id}")

    async def resolve_interrupt(
        self,
        thread_id: str,
        *,
        agent_id: str,
        approved: bool,
    ) -> None:
        await self._request(
            "POST",
            f"/threads/{thread_id}/resolve-interrupt",
            json_body={
                "agent_id": agent_id,
                "decisions": [{"type": "approve" if approved else "reject"}],
            },
        )

    async def stream_run(
        self,
        thread_id: str,
        *,
        agent_id: str,
        messages: list[dict[str, str]] | None = None,
        stream_modes: list[str] | None = None,
        user_timezone: str = "UTC",
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield (event_name, data_json_string) from the upstream SSE stream."""
        modes = stream_modes or ["messages-tuple", "updates"]
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "stream_mode": modes,
            "stream_subgraphs": True,
            "user_timezone": user_timezone,
        }
        if messages is not None:
            payload["messages"] = messages
        url = f"{self.base_url}/threads/{thread_id}/runs/stream"

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._headers("text/event-stream"),
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise DeepAgentsError(
                        response.status_code,
                        body.decode("utf-8", errors="replace"),
                    )

                event_name = ""
                data_lines: list[str] = []

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                    elif line == "" and data_lines:
                        yield event_name or "message", "\n".join(data_lines)
                        event_name = ""
                        data_lines = []

                if data_lines:
                    yield event_name or "message", "\n".join(data_lines)


def extract_text_from_message_chunk(chunk: dict[str, Any]) -> str:
    """Pull displayable text from an AIMessageChunk in messages-tuple stream."""
    content = chunk.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "".join(parts)
    return ""


def parse_interrupt_from_values(data: str) -> dict[str, Any] | None:
    """Extract human-in-the-loop interrupt payload from a values SSE event."""
    try:
        state = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(state, dict):
        return None

    raw = state.get("__interrupt__")
    if raw is None:
        for value in state.values():
            if isinstance(value, dict) and "__interrupt__" in value:
                raw = value["__interrupt__"]
                break
    if raw is None:
        return None

    items = raw if isinstance(raw, list) else [raw]
    first = items[0] if items else {}
    value = first.get("value", first) if isinstance(first, dict) else first

    tool = "tool"
    description = "This tool requires your approval before it runs."
    if isinstance(value, dict):
        tool = (
            value.get("tool_name")
            or value.get("name")
            or value.get("action_request", {}).get("action")
            or tool
        )
        description = value.get("description") or value.get("message") or description
        args = value.get("args") or value.get("arguments")
        if args:
            description = f"{description}\n\nArguments: {json.dumps(args, indent=2)[:800]}"
    elif isinstance(value, str):
        description = value

    return {
        "tool": str(tool),
        "description": str(description)[:1200],
        "interrupt_id": first.get("id") if isinstance(first, dict) else None,
    }


def parse_messages_event(data: str) -> str | None:
    """Return token text from a messages SSE payload, or None."""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    chunk = parsed[0]
    if not isinstance(chunk, dict):
        return None
    msg_type = chunk.get("type", "")
    if "AIMessageChunk" in msg_type or msg_type in ("ai", "AIMessage"):
        text = extract_text_from_message_chunk(chunk)
        return text if text else None
    return None
