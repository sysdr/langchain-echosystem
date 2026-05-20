"""LangSmith Deployment graph — used by langgraph.json for `langgraph up` / cloud deploy."""

from pathlib import Path

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"


def _instructions() -> str:
    path = AGENT_DIR / "AGENTS.md"
    return path.read_text(encoding="utf-8") if path.exists() else "You are a helpful assistant."


def web_search(query: str) -> str:
    """Search the web (configure Fleet MCP tools on Managed Deep Agents for production search)."""
    return f"Search query: {query}"


agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[web_search],
    system_prompt=_instructions(),
    checkpointer=MemorySaver(),
)
