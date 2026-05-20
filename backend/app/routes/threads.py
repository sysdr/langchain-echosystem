from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.deepagents_client import DeepAgentsClient, DeepAgentsError

router = APIRouter(prefix="/threads", tags=["threads"])


class CreateThreadRequest(BaseModel):
    agent_id: str | None = Field(
        default=None,
        description="Managed agent ID; defaults to MANAGED_AGENT_ID from env",
    )


@router.post("")
async def create_thread(body: CreateThreadRequest) -> dict[str, Any]:
    agent_id = body.agent_id or settings.managed_agent_id
    if not agent_id:
        raise HTTPException(
            status_code=400,
            detail="agent_id required (body or MANAGED_AGENT_ID env)",
        )
    try:
        client = DeepAgentsClient()
        return await client.create_thread(agent_id)
    except DeepAgentsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.get("/{thread_id}")
async def get_thread(thread_id: str) -> dict[str, Any]:
    try:
        client = DeepAgentsClient()
        return await client.get_thread(thread_id)
    except DeepAgentsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
