"""Integration test: spawn with redaction -> hatch with secrets file.

Verifies that PII/secret placeholders survive the full pipeline and are
restored on hatch when a secrets file is provided.

Marked ``@pytest.mark.integration`` -- requires ``gitleaks`` on PATH.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.common.enums import AgentType
from pynydus.engine.hatcher import hatch
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save
from pynydus.engine.pipeline import spawn

pytestmark = pytest.mark.integration


@pytest.fixture
def oc_with_secrets(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "soul.md").write_text("I am a research assistant.\n\nContact: alex@example.com\n")
    (src / "knowledge.md").write_text("The speed of light is 299792458 m/s.\n")
    (src / "config.json").write_text(
        '{"aws_access_key_id": "AKIAYRWSSQ3BPTB4DX7Z", "model": "gpt-4"}\n'
    )
    (src / "skill.md").write_text("# Summarize\n\nProduce a summary.\n")
    return src


def test_redaction_roundtrip(oc_with_secrets: Path, tmp_path: Path):
    config = NydusfileConfig(
        sources=[SourceDirective(agent_type="openclaw", path=str(oc_with_secrets))],
        redact=True,
    )
    egg, raw, logs = spawn(config, nydusfile_dir=tmp_path)

    assert egg.secrets.secrets, "Expected at least PII secrets to be detected"

    egg_path = tmp_path / "redacted.egg"
    save(egg, egg_path, raw_artifacts=raw, spawn_log=logs.get("spawn_log"))
    loaded = load(egg_path)

    env_file = tmp_path / "agent.env"
    env_lines = []
    for sec in loaded.secrets.secrets:
        env_lines.append(f"{sec.name}=restored-value-for-{sec.name}")
    env_file.write_text("\n".join(env_lines) + "\n")

    out_dir = tmp_path / "hatched"
    result = hatch(loaded, target=AgentType.OPENCLAW, output_dir=out_dir, secrets_path=env_file)

    all_output = " ".join(
        (out_dir / f).read_text() for f in result.files_created if (out_dir / f).exists()
    )
    for sec in loaded.secrets.secrets:
        assert sec.placeholder not in all_output, (
            f"Placeholder {sec.placeholder} should have been replaced"
        )
        assert f"restored-value-for-{sec.name}" in all_output


def test_no_redact(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "soul.md").write_text("I am an assistant.\n")
    (src / "config.json").write_text('{"key": "sk-secret-123"}\n')

    config = NydusfileConfig(
        sources=[SourceDirective(agent_type="openclaw", path=str(src))],
        redact=False,
    )
    egg, raw, _ = spawn(config, nydusfile_dir=tmp_path)
    assert len(egg.secrets.secrets) == 0
    assert "sk-secret-123" in raw.get("config.json", "")
