from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.deepagents_client import DeepAgentsClient, DeepAgentsError

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    description: str | None = None


@router.get("")
async def list_agents() -> list[dict[str, Any]]:
    if settings.resolved_runtime != "managed":
        return []
    try:
        client = DeepAgentsClient()
        return await client.list_agents()
    except DeepAgentsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.get("/configured")
async def get_configured_agent() -> dict[str, Any]:
    agent_id = settings.managed_agent_id
    if not agent_id:
        raise HTTPException(
            status_code=404,
            detail="MANAGED_AGENT_ID not set. Run scripts/provision_agent.py first.",
        )
    try:
        client = DeepAgentsClient()
        return await client.get_agent(agent_id)
    except DeepAgentsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
