"""Integration test: spawn -> sign -> save -> load -> verify -> hatch.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.common.enums import AgentType
from pynydus.engine.hatcher import hatch
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save, verify_egg_archive
from pynydus.engine.pipeline import spawn
from pynydus.security.signing import generate_keypair, load_private_key

pytestmark = pytest.mark.integration


@pytest.fixture
def openclaw_src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "SOUL.md").write_text("I am a research assistant.\n")
    (src / "MEMORY.md").write_text("Python 3.12 released Oct 2023.\n")
    (src / "skill.md").write_text("# Summarize\n\nProduce a summary.\n")
    return src


def test_signed_roundtrip(openclaw_src: Path, tmp_path: Path):
    config = NydusfileConfig(
        sources=[SourceDirective(agent_type="openclaw", path=str(openclaw_src))],
        redact=True,
    )
    egg, raw, logs = spawn(config, nydusfile_dir=tmp_path)

    key_dir = tmp_path / "keys"
    generate_keypair(key_dir)
    private_key = load_private_key(key_dir / "private.pem")

    egg_path = tmp_path / "signed.egg"
    save(egg, egg_path, raw_artifacts=raw, spawn_log=logs.get("spawn_log"), private_key=private_key)

    assert verify_egg_archive(egg_path) is True

    loaded = load(egg_path)
    assert loaded.manifest.signature != ""

    out_dir = tmp_path / "hatched"
    result = hatch(loaded, target=AgentType.OPENCLAW, output_dir=out_dir)
    assert "agent/SOUL.md" in result.files_created
    assert any(f.startswith("agent/skills/") for f in result.files_created)


def test_tampered_fails(openclaw_src: Path, tmp_path: Path):
    import shutil
    import tempfile
    import zipfile

    config = NydusfileConfig(
        sources=[SourceDirective(agent_type="openclaw", path=str(openclaw_src))],
        redact=True,
    )
    egg, raw, logs = spawn(config, nydusfile_dir=tmp_path)

    key_dir = tmp_path / "keys"
    generate_keypair(key_dir)
    private_key = load_private_key(key_dir / "private.pem")

    egg_path = tmp_path / "signed.egg"
    save(egg, egg_path, raw_artifacts=raw, spawn_log=logs.get("spawn_log"), private_key=private_key)

    with tempfile.NamedTemporaryFile(suffix=".egg", delete=False) as tf:
        tampered = Path(tf.name)
    with zipfile.ZipFile(egg_path, "r") as zr:
        with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as zw:
            for item in zr.infolist():
                if item.filename == "memory.json":
                    zw.writestr(item, b'{"memory":[]}')
                else:
                    zw.writestr(item, zr.read(item.filename))
    shutil.move(str(tampered), str(egg_path))

    assert verify_egg_archive(egg_path) is False
