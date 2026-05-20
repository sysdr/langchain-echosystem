from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO_ROOT / "agent"

RuntimeMode = Literal["auto", "managed", "local", "deployment"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    langsmith_api_key: str = ""
    langsmith_api_url: str = "https://api.smith.langchain.com"
    managed_agent_id: str = ""
    agent_runtime: RuntimeMode = "auto"
    langgraph_deployment_url: str = ""
    langgraph_assistant_id: str = ""
    require_hitl_approval: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    default_model: str = "anthropic:claude-sonnet-4-6"

    @property
    def deepagents_base_url(self) -> str:
        return f"{self.langsmith_api_url.rstrip('/')}/v1/deepagents"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_runtime(self) -> Literal["managed", "local", "deployment"]:
        if self.agent_runtime != "auto":
            return self.agent_runtime  # type: ignore[return-value]
        if self.langgraph_deployment_url:
            return "deployment"
        if self.managed_agent_id and self.langsmith_api_key:
            return "managed"
        return "local"


settings = Settings()
