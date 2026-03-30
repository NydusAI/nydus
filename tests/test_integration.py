"""Integration tests for features not covered by test_pipeline.py.

Covers:
- PII redaction with SSN patterns
- Skills directory round-trip (SKILL.md format in archive)
- In-memory secret injection (hatcher ordering)
- Egg version compatibility (v2.0)
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from pynydus.api.schemas import (
    RedactMode,
    SecretKind,
    SourceType,
)
from pynydus.api.skill_format import parse_skill_md
from pynydus.engine.hatcher import hatch
from pynydus.engine.packager import pack_with_raw, unpack
from pynydus.engine.pipeline import build


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def openclaw_project(tmp_path: Path) -> Path:
    proj = tmp_path / "oc"
    proj.mkdir()
    (proj / "soul.md").write_text(
        "I love espresso.\n\nI prefer morning meetings."
    )
    (proj / "skill.md").write_text(
        "# Greeting\nSay hello nicely.\n\n# Search\nSearch the web for answers."
    )
    return proj


class TestPIIRedactionE2E:
    def test_pii_redacted_in_spawn(self, tmp_path: Path):
        proj = tmp_path / "oc"
        proj.mkdir()
        (proj / "soul.md").write_text(
            "My friend John Smith lives at 123 Main St.\n\n"
            "His SSN is 123-45-6789."
        )
        (proj / "skill.md").write_text("# Greet\nSay hello")

        egg, _, _ = build(
            proj,
            source_type="openclaw",
            redact_mode=RedactMode.PII,
        )
        # Should have detected PII
        pii_secrets = [s for s in egg.secrets.secrets if s.kind == SecretKind.PII]
        assert len(pii_secrets) >= 1

        # Memory should have placeholders instead of raw PII
        all_memory_text = " ".join(m.text for m in egg.memory.memory)
        assert "123-45-6789" not in all_memory_text



# ---------------------------------------------------------------------------
# Skills directory round-trip
# ---------------------------------------------------------------------------


class TestSkillsDirectoryRoundTrip:
    def test_skill_content_preserved(self, openclaw_project: Path, tmp_path: Path):
        egg, artifacts, _ = build(
            openclaw_project,
            source_type="openclaw",
            redact_mode=RedactMode.NONE,
        )
        original_contents = {s.name: s.content for s in egg.skills.skills}

        egg_path = pack_with_raw(egg, tmp_path / "agent", artifacts)
        loaded = unpack(egg_path)

        for skill in loaded.skills.skills:
            assert skill.name in original_contents
            # Content should be in the SKILL.md body
            assert original_contents[skill.name] in skill.content

    def test_skill_md_format_in_archive(self, openclaw_project: Path, tmp_path: Path):
        egg, artifacts, _ = build(
            openclaw_project,
            source_type="openclaw",
            redact_mode=RedactMode.NONE,
        )
        egg_path = pack_with_raw(egg, tmp_path / "agent", artifacts)

        with zipfile.ZipFile(egg_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/SKILL.md"):
                    content = zf.read(name).decode()
                    # Should be parseable as Agent Skills format
                    parsed = parse_skill_md(content)
                    assert parsed.name


# ---------------------------------------------------------------------------
# Secret injection (new hatcher order)
# ---------------------------------------------------------------------------


class TestSecretInjectionNewOrder:
    def test_secrets_injected_into_egg_content(self, tmp_path: Path):
        """Secrets are resolved in-memory before hatcher writes files."""
        proj = tmp_path / "oc"
        proj.mkdir()
        (proj / "soul.md").write_text("Use key: placeholder here")
        (proj / "skill.md").write_text("# Auth\nUse {{SECRET_001}} to auth")
        (proj / "config.json").write_text(json.dumps({"api_key": "sk-abc123def"}))

        egg, artifacts, _ = build(
            proj,
            source_type="openclaw",
            redact_mode=RedactMode.PII,
        )

        assert egg.secrets.secrets, "Expected secret extraction to detect the API key"

        env_path = tmp_path / ".env"
        lines = [f"{s.name}=REAL_VALUE_{s.id}" for s in egg.secrets.secrets]
        env_path.write_text("\n".join(lines) + "\n")

        egg_path = pack_with_raw(egg, tmp_path / "agent", artifacts)
        loaded = unpack(egg_path)

        out = tmp_path / "hatched"
        result = hatch(
            loaded, target="openclaw", output_dir=out, secrets_path=env_path
        )

        for fname in result.files_created:
            fpath = out / fname
            if fpath.exists():
                try:
                    content = fpath.read_text()
                    assert "{{SECRET_" not in content, f"Leftover placeholder in {fname}"
                except UnicodeDecodeError:
                    pass

    def test_hatch_log_records_injections(self, tmp_path: Path):
        """Hatch log should record secret injection events."""
        proj = tmp_path / "oc"
        proj.mkdir()
        (proj / "soul.md").write_text("My SSN is 123-45-6789.")
        (proj / "skill.md").write_text("# Greet\nHello")

        egg, artifacts, _ = build(
            proj,
            source_type="openclaw",
            redact_mode=RedactMode.PII,
        )

        assert egg.secrets.secrets, "Expected Presidio to detect the SSN as PII"

        egg_path = pack_with_raw(egg, tmp_path / "agent", artifacts)
        loaded = unpack(egg_path)

        env_path = tmp_path / ".env"
        lines = [f"{s.name}=VALUE_{s.id}" for s in loaded.secrets.secrets
                 if s.required_at_hatch]
        env_path.write_text("\n".join(lines) + "\n")

        out = tmp_path / "hatched"
        result = hatch(
            loaded, target="openclaw", output_dir=out, secrets_path=env_path
        )
        assert isinstance(result.hatch_log, list)
        assert len(result.hatch_log) > 0, "Expected hatch log to record injection events"


# ---------------------------------------------------------------------------
# Egg version
# ---------------------------------------------------------------------------


class TestEggVersion:
    def test_new_eggs_have_version_2(self, openclaw_project: Path, tmp_path: Path):
        egg, _, _ = build(
            openclaw_project,
            source_type="openclaw",
            redact_mode=RedactMode.NONE,
        )
        assert egg.manifest.egg_version == "2.0"

