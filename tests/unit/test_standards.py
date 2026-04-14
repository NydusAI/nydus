"""Tests for pynydus.standards: loader, mcp, skills, a2a, apm, agents_md."""

from __future__ import annotations

import json

import pytest
from pynydus.api.schemas import (
    AgentSkill,
    McpModule,
    MemoryRecord,
    SecretRecord,
    SecretsModule,
)
from pynydus.common.enums import MemoryLabel, SecretKind
from pynydus.standards import a2a as a2a_mod
from pynydus.standards import agents_md as agents_md_mod
from pynydus.standards import apm as apm_mod
from pynydus.standards import load_spec
from pynydus.standards import mcp as mcp_mod
from pynydus.standards import skills as skills_mod

from conftest import make_egg

# =====================================================================
# _loader.py
# =====================================================================


class TestLoader:
    def test_load_mcp_spec(self):
        md, schema = load_spec("mcp")
        assert "MCP Server Configuration Spec" in md
        assert schema is not None
        assert schema["$id"] == "https://nydus.dev/schemas/mcp-config.json"
        assert "mcpServers" in schema["properties"]

    def test_load_agentskills_spec(self):
        md, schema = load_spec("agentskills")
        assert "Agent Skills Spec" in md
        assert schema is not None
        assert schema["required"] == ["name", "description"]

    def test_load_a2a_spec(self):
        md, schema = load_spec("a2a")
        assert "A2A Agent Card Spec" in md
        assert schema is not None
        assert "skills" in schema["required"]

    def test_load_apm_spec_no_schema(self):
        md, schema = load_spec("apm")
        assert "APM" in md
        assert schema is None

    def test_load_agents_spec(self):
        md, schema = load_spec("agents")
        assert "AGENTS.md Spec" in md
        assert schema is not None
        assert "has_prerequisites" in schema["required"]

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_spec("nonexistent-standard")


# =====================================================================
# mcp.py
# =====================================================================


class TestMcpStandard:
    @pytest.fixture
    def egg_with_mcp(self):
        return make_egg(
            mcp=McpModule(
                configs={
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                    },
                    "brave-search": {
                        "command": "npx",
                        "args": ["-y", "@anthropic/mcp-server-brave"],
                        "env": {"BRAVE_API_KEY": "test"},
                    },
                }
            ),
        )

    def test_validate_valid(self, egg_with_mcp):
        issues = mcp_mod.validate(egg_with_mcp)
        assert issues == []

    def test_validate_empty_configs(self, minimal_egg):
        issues = mcp_mod.validate(minimal_egg)
        assert issues == []

    def test_validate_invalid_server(self):
        egg = make_egg(mcp=McpModule(configs={"bad": {"env": {"X": "1"}}}))
        issues = mcp_mod.validate(egg)
        assert len(issues) > 0
        assert any("MCP schema" in i.message for i in issues)

    def test_extract(self, egg_with_mcp):
        result = mcp_mod.extract(egg_with_mcp)
        assert "mcp.json" in result
        doc = json.loads(result["mcp.json"])
        assert "mcpServers" in doc
        assert "filesystem" in doc["mcpServers"]
        assert "brave-search" in doc["mcpServers"]

    def test_extract_empty(self, minimal_egg):
        result = mcp_mod.extract(minimal_egg)
        assert result == {}

    def test_generate_same_as_extract(self, egg_with_mcp):
        assert mcp_mod.generate(egg_with_mcp) == mcp_mod.extract(egg_with_mcp)


# =====================================================================
# skills.py
# =====================================================================


class TestSkillsStandard:
    @pytest.fixture
    def egg_with_skills(self):
        return make_egg(
            skills=[
                AgentSkill(
                    name="code-review",
                    description="Reviews pull requests.",
                    body="Review the code.",
                    metadata={"id": "skill_001"},
                ),
                AgentSkill(
                    name="test-runner",
                    description="Runs test suites.",
                    body="Run the tests.",
                    metadata={"id": "skill_002"},
                ),
            ]
        )

    def test_validate_valid(self, egg_with_skills):
        issues = skills_mod.validate(egg_with_skills)
        assert issues == []

    def test_validate_empty(self, minimal_egg):
        issues = skills_mod.validate(minimal_egg)
        assert issues == []

    def test_validate_bad_name(self):
        egg = make_egg(
            skills=[
                AgentSkill(
                    name="UPPER CASE BAD",
                    description="desc",
                    body="body",
                )
            ]
        )
        issues = skills_mod.validate(egg)
        assert len(issues) > 0
        assert any("does not match" in i.message for i in issues)

    def test_extract(self, egg_with_skills):
        result = skills_mod.extract(egg_with_skills)
        assert "skills/code-review/SKILL.md" in result
        assert "skills/test-runner/SKILL.md" in result
        assert "code-review" in result["skills/code-review/SKILL.md"]

    def test_extract_empty(self, minimal_egg):
        result = skills_mod.extract(minimal_egg)
        assert result == {}


# =====================================================================
# a2a.py
# =====================================================================


class TestA2AStandard:
    @pytest.fixture
    def egg_with_card(self):
        card = {
            "name": "Test Agent",
            "description": "An agent for testing.",
            "version": "1.0",
            "supportedInterfaces": [],
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": [
                {
                    "id": "s1",
                    "name": "greet",
                    "description": "Greets users.",
                    "tags": ["greeting"],
                }
            ],
        }
        return make_egg(a2a_card=card)

    @pytest.fixture
    def egg_for_generation(self):
        return make_egg(
            agent_name="BookingBot",
            agent_description="Helps users book flights.",
            skills=[
                AgentSkill(
                    name="search-flights",
                    description="Search for available flights.",
                    body="Search logic here.",
                    metadata={"id": "skill_001", "tags": ["travel", "search"]},
                ),
            ],
        )

    def test_validate_valid(self, egg_with_card):
        issues = a2a_mod.validate(egg_with_card)
        assert issues == []

    def test_validate_missing_card(self, minimal_egg):
        issues = a2a_mod.validate(minimal_egg)
        assert issues == []

    def test_validate_bad_card(self):
        bad_card = {"name": "x"}
        egg = make_egg(a2a_card=bad_card)
        issues = a2a_mod.validate(egg)
        assert len(issues) > 0
        assert any("A2A agent card" in i.message for i in issues)

    def test_extract(self, egg_with_card):
        result = a2a_mod.extract(egg_with_card)
        assert "agent-card.json" in result
        doc = json.loads(result["agent-card.json"])
        assert doc["name"] == "Test Agent"

    def test_extract_missing(self, minimal_egg):
        result = a2a_mod.extract(minimal_egg)
        assert result == {}

    def test_generate_passthrough(self, egg_with_card):
        result = a2a_mod.generate(egg_with_card)
        doc = json.loads(result["agent-card.json"])
        assert doc["name"] == "Test Agent"

    def test_generate_from_egg_data(self, egg_for_generation):
        result = a2a_mod.generate(egg_for_generation)
        assert "agent-card.json" in result
        doc = json.loads(result["agent-card.json"])
        assert doc["name"] == "BookingBot"
        assert doc["description"] == "Helps users book flights."
        assert len(doc["skills"]) == 1
        assert doc["skills"][0]["name"] == "search-flights"
        assert doc["skills"][0]["tags"] == ["travel", "search"]

    def test_generate_fallback_name_from_agent_type(self, minimal_egg):
        result = a2a_mod.generate(minimal_egg)
        doc = json.loads(result["agent-card.json"])
        assert doc["name"] == "openclaw"

    def test_generate_fallback_description_from_persona(self):
        egg = make_egg(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="I am a helpful travel assistant.",
                    label=MemoryLabel.PERSONA,
                    agent_type="openclaw",
                    source_store="PERSONA.md",
                )
            ],
        )
        result = a2a_mod.generate(egg)
        doc = json.loads(result["agent-card.json"])
        assert "travel assistant" in doc["description"]

    def test_generate_with_llm_fn(self, egg_for_generation):
        def mock_llm(card):
            card["name"] = "LLM-Enhanced Agent"
            return card

        result = a2a_mod.generate(egg_for_generation, llm_fn=mock_llm)
        doc = json.loads(result["agent-card.json"])
        assert doc["name"] == "LLM-Enhanced Agent"

    def test_generated_card_validates(self, egg_for_generation):
        result = a2a_mod.generate(egg_for_generation)
        doc = json.loads(result["agent-card.json"])
        egg_for_generation.a2a_card = doc
        issues = a2a_mod.validate(egg_for_generation)
        assert issues == []


# =====================================================================
# apm.py
# =====================================================================


class TestApmStandard:
    def test_extract_present(self):
        yml = "name: my-agent\nversion: 1.0.0\n"
        egg = make_egg(apm_yml=yml)
        result = apm_mod.extract(egg)
        assert result == {"apm.yml": yml}

    def test_extract_absent(self, minimal_egg):
        result = apm_mod.extract(minimal_egg)
        assert result == {}


# =====================================================================
# agents_md.py
# =====================================================================


class TestAgentsMdStandard:
    @pytest.fixture
    def egg_with_agents_md(self):
        md = (
            "# Deploying This Agent\n\n"
            "## Prerequisites\n- Nydus CLI >= 0.0.7\n\n"
            "## Hatch\n```\nnydus hatch agent.egg\n```\n"
        )
        return make_egg(agents_md=md)

    @pytest.fixture
    def rich_egg(self):
        return make_egg(
            agent_name="TravelBot",
            skills=[
                AgentSkill(
                    name="book-flight",
                    description="Books flights for users.",
                    body="Booking logic.",
                    metadata={"id": "s1"},
                ),
            ],
            mcp=McpModule(
                configs={
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                    }
                }
            ),
            secrets=SecretsModule(
                secrets=[
                    SecretRecord(
                        id="sec_001",
                        placeholder="{{SECRET_001}}",
                        kind=SecretKind.CREDENTIAL,
                        name="BOOKING_API_KEY",
                        required_at_hatch=True,
                        description="API key for booking service",
                    )
                ]
            ),
        )

    def test_validate_valid(self, egg_with_agents_md):
        issues = agents_md_mod.validate(egg_with_agents_md)
        assert issues == []

    def test_validate_missing(self, minimal_egg):
        issues = agents_md_mod.validate(minimal_egg)
        assert issues == []

    def test_validate_missing_sections(self):
        egg = make_egg(agents_md="# Just a title\n\nNo required sections.\n")
        issues = agents_md_mod.validate(egg)
        assert len(issues) > 0
        assert any("True was expected" in i.message for i in issues)

    def test_extract(self, egg_with_agents_md):
        result = agents_md_mod.extract(egg_with_agents_md)
        assert "AGENTS.md" in result
        assert "Prerequisites" in result["AGENTS.md"]

    def test_extract_missing(self, minimal_egg):
        result = agents_md_mod.extract(minimal_egg)
        assert result == {}

    def test_generate_passthrough(self, egg_with_agents_md):
        result = agents_md_mod.generate(egg_with_agents_md)
        assert result["AGENTS.md"] == egg_with_agents_md.agents_md

    def test_generate_from_egg_data(self, rich_egg):
        result = agents_md_mod.generate(rich_egg)
        md = result["AGENTS.md"]
        assert "## Prerequisites" in md
        assert "## Hatch" in md
        assert "## Required Secrets" in md
        assert "BOOKING_API_KEY" in md
        assert "## MCP Servers" in md
        assert "filesystem" in md
        assert "## Skills" in md
        assert "book-flight" in md
        assert "## Verify" in md

    def test_generate_minimal(self, minimal_egg):
        result = agents_md_mod.generate(minimal_egg)
        md = result["AGENTS.md"]
        assert "## Prerequisites" in md
        assert "## Hatch" in md
        assert "MCP Servers" not in md
        assert "Required Secrets" not in md

    def test_generate_with_llm_fn(self, rich_egg):
        def mock_llm(draft):
            return draft + "\n---\nLLM-enhanced.\n"

        result = agents_md_mod.generate(rich_egg, llm_fn=mock_llm)
        assert "LLM-enhanced" in result["AGENTS.md"]

    def test_generated_validates(self, rich_egg):
        result = agents_md_mod.generate(rich_egg)
        rich_egg.agents_md = result["AGENTS.md"]
        issues = agents_md_mod.validate(rich_egg)
        assert issues == []
