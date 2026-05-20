from app.config import settings
from app.runtime.base import AgentRuntime
from app.runtime.deployment import DeploymentRuntime
from app.runtime.local import LocalRuntime
from app.runtime.managed import ManagedRuntime


def get_runtime() -> AgentRuntime:
    mode = settings.resolved_runtime
    if mode == "managed":
        return ManagedRuntime()
    if mode == "deployment":
        return DeploymentRuntime()
    return LocalRuntime()
