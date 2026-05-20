#!/usr/bin/env python3
"""Create or update a Managed Deep Agent from the repo agent/ directory."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO_ROOT / "agent"
ENV_FILE = REPO_ROOT / ".env"


def load_instructions() -> str:
    path = AGENT_DIR / "AGENTS.md"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    return path.read_text(encoding="utf-8")


def load_tools() -> dict:
    path = AGENT_DIR / "tools.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_subagents() -> dict[str, str]:
    sub_dir = AGENT_DIR / "subagents"
    if not sub_dir.exists():
        return {}
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(sub_dir.glob("*.md"))
    }


def load_skills() -> dict[str, str]:
    skills_dir = AGENT_DIR / "skills"
    if not skills_dir.exists():
        return {}
    files: dict[str, str] = {}
    for skill_md in skills_dir.rglob("SKILL.md"):
        rel = skill_md.relative_to(skills_dir)
        key = str(rel.parent).replace("\\", "/")
        files[key] = skill_md.read_text(encoding="utf-8")
    return files


def apply_hitl_config(tools_config: dict) -> dict:
    """Toggle web-search human approval from REQUIRE_HITL_APPROVAL env."""
    require = os.environ.get("REQUIRE_HITL_APPROVAL", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    config = dict(tools_config)
    interrupt = dict(config.get("interrupt_config") or {})
    interrupt["https://tools.langchain.com::tavily_web_search::Fleet"] = require
    config["interrupt_config"] = interrupt
    return config


def build_payload(
    *,
    name: str,
    description: str,
    model_id: str,
) -> dict:
    tools_config = apply_hitl_config(load_tools())
    payload: dict = {
        "name": name,
        "description": description,
        "runtime": {"model": {"model_id": model_id}},
        "instructions": load_instructions(),
        "tools": tools_config,
    }
    subagents = load_subagents()
    skills = load_skills()
    if subagents:
        payload["subagents"] = subagents
    if skills:
        payload["skills"] = skills
    return payload


def update_env_file(agent_id: str) -> None:
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    key = "MANAGED_AGENT_ID"
    found = False
    out: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={agent_id}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={agent_id}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {key}={agent_id} to {ENV_FILE}")


def extract_agent_id(response: dict) -> str:
    for key in ("id", "agent_id"):
        if response.get(key):
            return str(response[key])
    agent = response.get("agent")
    if isinstance(agent, dict):
        for key in ("id", "agent_id"):
            if agent.get(key):
                return str(agent[key])
    raise ValueError(f"Could not find agent id in response: {response}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision Managed Deep Agent")
    parser.add_argument("--name", default="research-assistant")
    parser.add_argument(
        "--description",
        default="Research assistant with web search, URL reading, and fact-checking subagent.",
    )
    parser.add_argument("--model", default=os.environ.get("DEFAULT_MODEL", "anthropic:claude-sonnet-4-6"))
    parser.add_argument("--update", metavar="AGENT_ID", help="PATCH existing agent instead of create")
    args = parser.parse_args()

    api_key = os.environ.get("LANGSMITH_API_KEY", "")
    api_url = os.environ.get("LANGSMITH_API_URL", "https://api.smith.langchain.com").rstrip("/")
    base = f"{api_url}/v1/deepagents"

    if not api_key:
        print("Error: set LANGSMITH_API_KEY", file=sys.stderr)
        return 1

    payload = build_payload(
        name=args.name,
        description=args.description,
        model_id=args.model,
    )
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=120.0) as client:
        if args.update:
            url = f"{base}/agents/{args.update}"
            response = client.patch(url, headers=headers, json=payload)
            action = "Updated"
            agent_id = args.update
        else:
            url = f"{base}/agents"
            response = client.post(url, headers=headers, json=payload)
            action = "Created"

        if response.status_code >= 400:
            print(f"Error {response.status_code}: {response.text}", file=sys.stderr)
            return 1

        data = response.json()
        if not args.update:
            agent_id = extract_agent_id(data)

    print(f"{action} agent: {agent_id}")
    if data.get("revision"):
        print(f"Revision: {data['revision']}")
    update_env_file(agent_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
