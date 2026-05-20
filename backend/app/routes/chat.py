import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.deepagents_client import DeepAgentsError
from app.runtime import get_runtime

router = APIRouter(tags=["chat"])


class StreamChatRequest(BaseModel):
    thread_id: str
    message: str
    user_timezone: str = "UTC"


class StreamResumeRequest(BaseModel):
    thread_id: str
    user_timezone: str = "UTC"


class ResolveInterruptRequest(BaseModel):
    thread_id: str
    approved: bool
    agent_id: str | None = None


class NewConversationResponse(BaseModel):
    thread_id: str
    agent_id: str


async def _stream_events(runtime, thread_id: str, message: str, user_timezone: str):
    async for event_name, data in runtime.stream_chat(
        thread_id, message, user_timezone=user_timezone
    ):
        yield _format_sse(event_name, data)
    yield {"event": "done", "data": "{}"}


async def _resume_events(runtime, thread_id: str, user_timezone: str):
    async for event_name, data in runtime.stream_resume(
        thread_id, user_timezone=user_timezone
    ):
        yield _format_sse(event_name, data)
    yield {"event": "done", "data": "{}"}


def _format_sse(event_name: str, data: str) -> dict:
    if event_name == "token":
        return {"event": "token", "data": data}
    if event_name == "interrupt":
        return {"event": "interrupt", "data": data}
    return {"event": event_name or "message", "data": data}


@router.post("/chat/stream")
async def stream_chat(body: StreamChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    runtime = get_runtime()

    async def event_generator():
        try:
            async for item in _stream_events(
                runtime, body.thread_id, body.message.strip(), body.user_timezone
            ):
                yield item
        except DeepAgentsError as e:
            yield {
                "event": "error",
                "data": json.dumps({"detail": e.detail, "status": e.status_code}),
            }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"detail": str(e), "status": 500}),
            }

    return EventSourceResponse(event_generator())


@router.post("/chat/resume-stream")
async def resume_stream(body: StreamResumeRequest):
    runtime = get_runtime()

    async def event_generator():
        try:
            async for item in _resume_events(
                runtime, body.thread_id, body.user_timezone
            ):
                yield item
        except DeepAgentsError as e:
            yield {
                "event": "error",
                "data": json.dumps({"detail": e.detail, "status": e.status_code}),
            }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"detail": str(e), "status": 500}),
            }

    return EventSourceResponse(event_generator())


@router.post("/chat/resolve-interrupt", status_code=204)
async def resolve_interrupt(body: ResolveInterruptRequest):
    runtime = get_runtime()
    try:
        await runtime.resolve_interrupt(
            body.thread_id,
            approved=body.approved,
            agent_id=body.agent_id,
        )
    except DeepAgentsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/conversations", response_model=NewConversationResponse)
async def new_conversation() -> NewConversationResponse:
    runtime = get_runtime()
    try:
        conv = await runtime.create_conversation()
    except DeepAgentsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return NewConversationResponse(
        thread_id=str(conv["thread_id"]),
        agent_id=str(conv["agent_id"]),
    )
