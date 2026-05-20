from fastapi import APIRouter

from app.config import settings
from app.runtime import get_runtime

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    runtime = get_runtime()
    ready = False
    if settings.resolved_runtime == "managed":
        ready = bool(settings.langsmith_api_key and settings.managed_agent_id)
    elif settings.resolved_runtime == "deployment":
        ready = bool(settings.langgraph_deployment_url and settings.langgraph_assistant_id)
    else:
        ready = True

    return {
        "status": "ok",
        "runtime": settings.resolved_runtime,
        "runtime_active": runtime.mode,
        "ready": ready,
        "api_key_configured": bool(settings.langsmith_api_key),
        "managed_agent_id_configured": bool(settings.managed_agent_id),
        "deployment_configured": bool(settings.langgraph_deployment_url),
        "hitl_enabled": settings.require_hitl_approval,
        **runtime.health_extra(),
    }
