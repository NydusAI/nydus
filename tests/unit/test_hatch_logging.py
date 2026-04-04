"""Tests for hatch pipeline logging.

Verifies that the hatch pipeline threads a hatch_log through all stages:
- Secret substitution entries
- LLM refinement entries
- Warnings from LLM refinement
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import (
    Egg,
    Manifest,
    MemoryModule,
    MemoryRecord,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import (
    AgentType,
    Bucket,
    InjectionMode,
    MemoryLabel,
    SecretKind,
)
from pynydus.engine.hatcher import (
    _substitute_secrets,
    hatch,
)


@pytest.fixture
def sample_egg() -> Egg:
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(UTC),
            agent_type=AgentType.OPENCLAW,
            included_modules=[Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET],
            source_metadata={"source_dir": "/tmp/test"},
        ),
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="search",
                    agent_type=AgentType.OPENCLAW,
                    content="Use key={{SECRET_001}} to auth",
                )
            ]
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Connect with {{SECRET_002}}",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="soul.md",
                )
            ]
        ),
        secrets=SecretsModule(
            secrets=[
                SecretRecord(
                    id="secret_001",
                    placeholder="{{SECRET_001}}",
                    kind=SecretKind.CREDENTIAL,
                    name="API_KEY",
                    required_at_hatch=True,
                    injection_mode=InjectionMode.ENV,
                ),
                SecretRecord(
                    id="secret_002",
                    placeholder="{{SECRET_002}}",
                    kind=SecretKind.CREDENTIAL,
                    name="DB_PASS",
                    required_at_hatch=True,
                    injection_mode=InjectionMode.ENV,
                ),
            ]
        ),
    )


class TestSubstituteSecrets:
    """Test that _substitute_secrets replaces placeholders in file contents."""

    def test_replaces_in_files(self):
        files = {
            "config.env": "KEY={{SECRET_001}}\nDB={{SECRET_002}}",
            "readme.md": "No secrets here.",
        }
        placeholder_map = {"{{SECRET_001}}": "sk-123", "{{SECRET_002}}": "pw"}
        result = _substitute_secrets(files, placeholder_map)

        assert "sk-123" in result["config.env"]
        assert "pw" in result["config.env"]
        assert "{{SECRET_001}}" not in result["config.env"]
        assert result["readme.md"] == "No secrets here."

    def test_no_change_when_no_placeholders(self):
        files = {"readme.md": "No secrets here."}
        placeholder_map = {"{{SECRET_001}}": "sk-123"}
        result = _substitute_secrets(files, placeholder_map)
        assert result["readme.md"] == "No secrets here."


class TestHatchPipelineLogging:
    """Test hatch_log on HatchResult after full pipeline."""

    def test_hatch_populates_log_with_secrets(self, tmp_path: Path):
        """Full hatch() populates hatch_log with secret_injection entries."""
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="skill_001",
                        name="search",
                        agent_type=AgentType.OPENCLAW,
                        content="Use key={{SECRET_001}} to auth",
                    )
                ]
            ),
            memory=MemoryModule(),
            secrets=SecretsModule(
                secrets=[
                    SecretRecord(
                        id="secret_001",
                        placeholder="{{SECRET_001}}",
                        kind=SecretKind.CREDENTIAL,
                        name="API_KEY",
                        required_at_hatch=True,
                        injection_mode=InjectionMode.ENV,
                    )
                ]
            ),
        )

        secrets_file = tmp_path / ".env"
        secrets_file.write_text("API_KEY=sk-test-123")

        mock_render = RenderResult(
            files={"skill.md": "# search\n\nUse key={{SECRET_001}} to auth\n"},
        )

        with patch("pynydus.engine.hatcher._get_hatcher") as mock_get:
            mock_connector = MagicMock()
            mock_connector.render.return_value = mock_render
            mock_get.return_value = mock_connector

            result = hatch(
                egg,
                target="letta",
                output_dir=out_dir,
                secrets_path=secrets_file,
            )

        assert len(result.hatch_log) >= 1
        assert any(e["type"] == "secret_injection" for e in result.hatch_log)

    def test_hatch_log_has_transform_entries_without_secrets(self, tmp_path: Path):
        """When no secrets are injected, hatch_log still has transform entries."""
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="skill_001",
                        name="search",
                        agent_type=AgentType.OPENCLAW,
                        content="no placeholders here",
                    )
                ]
            ),
        )

        mock_render = RenderResult(
            files={"readme.md": "Hello\n"},
        )

        with patch("pynydus.engine.hatcher._get_hatcher") as mock_get:
            mock_connector = MagicMock()
            mock_connector.render.return_value = mock_render
            mock_get.return_value = mock_connector

            result = hatch(
                egg,
                target="letta",
                output_dir=out_dir,
            )

        transform_entries = [e for e in result.hatch_log if e["type"] == "render_from_modules"]
        assert len(transform_entries) == 1
        assert transform_entries[0]["phase"] == "render"

    def test_hatch_log_serializable(self, sample_egg: Egg, tmp_path: Path):
        """hatch_log entries are JSON-serializable."""
        out_dir = tmp_path / "output"

        secrets_file = tmp_path / ".env"
        secrets_file.write_text("API_KEY=sk-test-123\nDB_PASS=hunter2")

        mock_render = RenderResult(
            files={"config.env": "KEY={{SECRET_001}}\n"},
        )

        with patch("pynydus.engine.hatcher._get_hatcher") as mock_get:
            mock_connector = MagicMock()
            mock_connector.render.return_value = mock_render
            mock_get.return_value = mock_connector

            result = hatch(
                sample_egg,
                target="letta",
                output_dir=out_dir,
                secrets_path=secrets_file,
            )

        serialized = json.dumps(result.hatch_log, indent=2)
        roundtripped = json.loads(serialized)
        assert roundtripped == result.hatch_log


class TestHatchModes:
    """Phase 2–3: rebuild vs passthrough mode."""

    def test_passthrough_mode_replays_raw_snapshot(self, tmp_path: Path):
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="skill_001",
                        name="search",
                        agent_type=AgentType.OPENCLAW,
                        content="search tool",
                    )
                ]
            ),
        )
        raw = {"skill.md": "# search\n\nsearch tool\n"}

        result = hatch(
            egg,
            target="openclaw",
            output_dir=out_dir,
            mode="passthrough",
            raw_artifacts=raw,
        )

        assert any(e["type"] == "raw_snapshot" for e in result.hatch_log)
        render_entries = [e for e in result.hatch_log if e["type"] == "render_from_modules"]
        assert len(render_entries) == 0

    def test_rebuild_mode_always_uses_connector(self, tmp_path: Path):
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="skill_001",
                        name="search",
                        agent_type=AgentType.OPENCLAW,
                        content="search tool",
                    )
                ]
            ),
        )

        mock_render = RenderResult(
            files={"skill.md": "search tool\n"},
        )

        with patch("pynydus.engine.hatcher._get_hatcher") as mock_get:
            mock_connector = MagicMock()
            mock_connector.render.return_value = mock_render
            mock_get.return_value = mock_connector

            result = hatch(egg, target="openclaw", output_dir=out_dir, mode="rebuild")

        assert not any(e["type"] == "raw_snapshot" for e in result.hatch_log)
        render_entries = [e for e in result.hatch_log if e["type"] == "render_from_modules"]
        assert len(render_entries) == 1

    def test_passthrough_mode_rejects_cross_platform(self, tmp_path: Path):
        from pynydus.api.errors import HatchError

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
        )
        raw = {"soul.md": "content"}

        with pytest.raises(HatchError, match="passthrough"):
            hatch(
                egg,
                target="letta",
                output_dir=tmp_path / "out",
                mode="passthrough",
                raw_artifacts=raw,
            )

    def test_passthrough_mode_rejects_empty_raw(self, tmp_path: Path):
        from pynydus.api.errors import HatchError

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
        )

        with pytest.raises(HatchError, match="raw artifacts"):
            hatch(
                egg,
                target="openclaw",
                output_dir=tmp_path / "out",
                mode="passthrough",
            )

    def test_passthrough_mode_writes_raw_files_to_disk(self, tmp_path: Path):
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL, Bucket.MEMORY],
            ),
        )
        raw = {"soul.md": "I am a soul.", "knowledge.md": "Facts here."}

        result = hatch(
            egg,
            target="openclaw",
            output_dir=out_dir,
            mode="passthrough",
            raw_artifacts=raw,
        )

        assert "soul.md" in result.files_created
        assert "knowledge.md" in result.files_created
        assert (out_dir / "soul.md").read_text() == "I am a soul."
        assert (out_dir / "knowledge.md").read_text() == "Facts here."

    def test_rebuild_mode_creates_expected_files(self, tmp_path: Path):
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL, Bucket.MEMORY],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="Test",
                        agent_type=AgentType.OPENCLAW,
                        content="Do it.",
                    ),
                ]
            ),
            memory=MemoryModule(
                memory=[
                    MemoryRecord(
                        id="m1",
                        text="A preference.",
                        label=MemoryLabel.PERSONA,
                        agent_type="openclaw",
                        source_store="soul.md",
                    ),
                ]
            ),
        )

        result = hatch(egg, target="openclaw", output_dir=out_dir)

        assert "soul.md" in result.files_created
        assert "skill.md" in result.files_created


class TestHatchLogWrittenByPipeline:
    """Phase 7: hatch_log.json is written by the pipeline."""

    def test_hatch_log_json_created_in_output(self, tmp_path: Path):
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="skill_001",
                        name="search",
                        agent_type=AgentType.OPENCLAW,
                        content="search tool",
                    )
                ]
            ),
        )

        mock_render = RenderResult(
            files={"agent_state.json": "{}\n"},
        )

        with patch("pynydus.engine.hatcher._get_hatcher") as mock_get:
            mock_connector = MagicMock()
            mock_connector.render.return_value = mock_render
            mock_get.return_value = mock_connector

            hatch(egg, target="letta", output_dir=out_dir)

        log_path = out_dir / "logs" / "hatch_log.json"
        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert isinstance(data, list)
        assert any(e["type"] == "render_from_modules" for e in data)

    def test_passthrough_mode_also_writes_log(self, tmp_path: Path):
        out_dir = tmp_path / "output"

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="skill_001",
                        name="search",
                        agent_type=AgentType.OPENCLAW,
                        content="search tool",
                    )
                ]
            ),
        )
        raw = {"skill.md": "search tool\n"}

        hatch(
            egg,
            target="openclaw",
            output_dir=out_dir,
            mode="passthrough",
            raw_artifacts=raw,
        )

        log_path = out_dir / "logs" / "hatch_log.json"
        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert any(e["type"] == "raw_snapshot" for e in data)
