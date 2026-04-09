"""Shared fixtures for Letta hatch layout integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save
from pynydus.engine.pipeline import spawn

PERSONA_TEXT = "I specialize in machine learning research and paper analysis."
HUMAN_TEXT = "The user is a PhD student studying computer vision at Stanford."
SYSTEM_PROMPT = (
    "You are a research assistant. Be thorough and cite sources. "
    "Always provide paper titles and publication years."
)
CUSTOM_TOOL_CODE = (
    "def search_papers(query: str) -> str:\n"
    '    """Search for academic papers matching the query."""\n'
    "    return query\n"
)
CUSTOM_TOOL_NAME = "search_papers"
MCP_SERVER_NAME = "arxiv"
MCP_SERVER_CMD = "npx"
MCP_SERVER_ARGS = ["@modelcontextprotocol/server-arxiv"]
ENV_VAR_KEY = "SEARCH_API_KEY"
ENV_VAR_VALUE = "sk-test-api-key-123"
MESSAGE_ASSISTANT = "Hello, how can I help with your research?"
MESSAGE_USER = "Find recent papers on vision transformers."


def make_af_data() -> dict:
    """Build a realistic AgentFileSchema-shaped dict."""
    return {
        "agents": [
            {
                "id": "agent-abc",
                "name": "research_bot",
                "system": SYSTEM_PROMPT,
                "agent_type": "letta_v1_agent",
                "description": "A bot that helps with ML research.",
                "block_ids": ["blk-0", "blk-1"],
                "tool_ids": ["tool-0", "tool-1"],
                "tool_rules": [
                    {"type": "TerminalToolRule", "tool_name": "send_message"}
                ],
                "tags": ["research", "ml"],
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": MESSAGE_ASSISTANT}],
                        "created_at": "2024-06-01T10:00:00Z",
                    },
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": MESSAGE_USER}],
                        "created_at": "2024-06-01T10:01:00Z",
                    },
                ],
                "in_context_message_ids": [],
                "tool_exec_environment_variables": {ENV_VAR_KEY: ENV_VAR_VALUE},
                "llm_config": {
                    "model": "gpt-4o",
                    "model_endpoint": "https://api.openai.com/v1",
                    "context_window": 128000,
                },
                "embedding_config": {
                    "embedding_model": "text-embedding-3-small",
                    "embedding_dim": 1536,
                },
            }
        ],
        "blocks": [
            {
                "id": "blk-0",
                "label": "persona",
                "value": PERSONA_TEXT,
                "limit": 5000,
                "is_template": False,
            },
            {
                "id": "blk-1",
                "label": "human",
                "value": HUMAN_TEXT,
                "limit": 5000,
                "is_template": False,
            },
        ],
        "tools": [
            {
                "id": "tool-0",
                "name": "send_message",
                "source_code": None,
                "tool_type": "letta_core",
                "source_type": "python",
                "json_schema": {"name": "send_message"},
            },
            {
                "id": "tool-1",
                "name": CUSTOM_TOOL_NAME,
                "source_code": CUSTOM_TOOL_CODE,
                "tool_type": "custom",
                "source_type": "python",
                "json_schema": {"name": CUSTOM_TOOL_NAME},
            },
        ],
        "groups": [],
        "files": [],
        "sources": [],
        "mcp_servers": [
            {
                "server_name": MCP_SERVER_NAME,
                "command": MCP_SERVER_CMD,
                "args": MCP_SERVER_ARGS,
            }
        ],
        "skills": [],
        "metadata": {"version": "1.0"},
    }


def write_rich_letta(d: Path) -> Path:
    """Create a rich Letta workspace with a real .af AgentFile."""
    d.mkdir(parents=True, exist_ok=True)
    af_data = make_af_data()
    (d / "agent.af").write_text(json.dumps(af_data, indent=2) + "\n")
    return d


def spawn_rich_letta(tmp_path: Path):
    """Write, spawn, save, and load a rich Letta workspace.

    Returns (loaded_egg, raw_artifacts).
    """
    src = tmp_path / "source"
    write_rich_letta(src)

    config = NydusfileConfig(
        sources=[SourceDirective(agent_type="letta", path=str(src))],
        redact=False,
    )
    egg, raw_artifacts, logs = spawn(config, nydusfile_dir=tmp_path)
    egg_path = tmp_path / "test.egg"
    save(egg, egg_path, raw_artifacts=raw_artifacts, spawn_log=logs.get("spawn_log"))
    loaded = load(egg_path, include_raw=True)
    return loaded, raw_artifacts
