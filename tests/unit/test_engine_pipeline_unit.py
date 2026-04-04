"""Unit tests for the spawn pipeline (engine/pipeline.py).

Tests assert on Egg *output* — what fields are populated, what content
survives — rather than checking whether mocks were called.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from pynydus.api.errors import NydusfileError
from pynydus.api.schemas import MemoryModule, MemoryRecord, SkillRecord, SkillsModule
from pynydus.common.enums import AgentType, MemoryLabel, SecretKind
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.pipeline import spawn


def _oc_config(path: Path, **kw) -> NydusfileConfig:
    return NydusfileConfig(
        sources=[SourceDirective(agent_type="openclaw", path=str(path))],
        **kw,
    )


@pytest.fixture
def src(tmp_path: Path) -> Path:
    d = tmp_path / "src"
    d.mkdir()
    (d / "soul.md").write_text("I am helpful.")
    (d / "knowledge.md").write_text("Sky is blue.")
    (d / "skill.md").write_text("# Greet\nSay hello.")
    return d


class TestSpawnerDispatch:
    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_single_source(self, _gl, src: Path):
        config = _oc_config(src, redact=False)
        egg, raw, _logs = spawn(config, nydusfile_dir=src.parent)
        assert egg.manifest.agent_type == AgentType.OPENCLAW
        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 1
        assert "soul.md" in raw

    def test_multi_source_rejected(self, tmp_path: Path):
        config = NydusfileConfig(
            sources=[
                SourceDirective(agent_type="openclaw", path=str(tmp_path)),
                SourceDirective(agent_type="letta", path=str(tmp_path)),
            ],
            redact=False,
        )
        with pytest.raises(NydusfileError, match="Only one SOURCE"):
            spawn(config, nydusfile_dir=tmp_path)


class TestRedaction:
    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_redact_true(self, _ensure, src: Path):
        (src / "config.json").write_text('{"aws_access_key_id": "AKIAYRWSSQ3BPTB4DX7Z"}')
        config = _oc_config(src, redact=True)
        egg, raw, logs = spawn(config, nydusfile_dir=src.parent)
        has_credential = any(s.kind == SecretKind.CREDENTIAL for s in egg.secrets.secrets)
        has_pii = any(s.kind == SecretKind.PII for s in egg.secrets.secrets)
        assert has_credential or has_pii, "redact=True should produce secrets"
        all_content = " ".join(raw.values())
        assert "{{SECRET_" in all_content or "{{PII_" in all_content
        assert len(logs["spawn_log"]) >= 1

    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_redact_false(self, _ensure, src: Path):
        config = _oc_config(src, redact=False)
        egg, raw, _logs = spawn(config, nydusfile_dir=src.parent)
        assert len(egg.secrets.secrets) == 0
        assert "I am helpful." in raw["soul.md"]


class TestLLMRefinement:
    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    @patch("pynydus.engine.refinement.refine_memory")
    @patch("pynydus.engine.refinement.refine_skills")
    def test_with_llm(self, mock_sk, mock_mem, _gl, src: Path):
        from pynydus.llm import LLMTierConfig

        def _modify_skills(s, cfg, **kw):
            for sk in s.skills:
                sk.name = "LLM-Polished"
            return s

        def _modify_memory(m, cfg, **kw):
            for rec in m.memory:
                rec.text = "LLM-Refined: " + rec.text
            return m

        mock_sk.side_effect = _modify_skills
        mock_mem.side_effect = _modify_memory

        tier = LLMTierConfig(provider="openai", model="gpt-4o", api_key="sk-test")
        config = _oc_config(src, redact=False)
        egg, _, _ = spawn(config, nydusfile_dir=src.parent, llm_config=tier)
        assert all(s.name == "LLM-Polished" for s in egg.skills.skills)
        assert all(m.text.startswith("LLM-Refined:") for m in egg.memory.memory)

    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_without_llm(self, _gl, src: Path):
        config = _oc_config(src, redact=False)
        egg, _, _ = spawn(config, nydusfile_dir=src.parent)
        texts = {m.text for m in egg.memory.memory}
        assert "I am helpful." in texts or any("helpful" in t for t in texts)


class TestBaseEggMerge:
    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    @patch("pynydus.engine.pipeline._resolve_base_egg")
    def test_from_present(self, mock_resolve, _gl, src: Path):
        from pynydus.api.schemas import EggPartial, SecretsModule

        base_partial = EggPartial(
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="base_s1",
                        name="base_skill",
                        agent_type="openclaw",
                        content="Base content.",
                    ),
                ]
            ),
            memory=MemoryModule(
                memory=[
                    MemoryRecord(
                        id="base_m1",
                        text="Base fact.",
                        label=MemoryLabel.STATE,
                        agent_type="openclaw",
                        source_store="base.md",
                    ),
                ]
            ),
            secrets=SecretsModule(),
            source_metadata={"base_egg": "test.egg"},
            raw_artifacts={},
        )
        mock_resolve.return_value = (base_partial, AgentType.OPENCLAW)

        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            base_egg="base.egg",
            redact=False,
        )
        egg, _, _ = spawn(config, nydusfile_dir=src.parent)
        skill_names = [s.name for s in egg.skills.skills]
        assert "base_skill" in skill_names
        mem_texts = [m.text for m in egg.memory.memory]
        assert "Base fact." in mem_texts
        assert len(egg.skills.skills) >= 2
        assert len(egg.memory.memory) >= 2

    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_no_from(self, _gl, src: Path):
        config = _oc_config(src, redact=False)
        egg, _, _ = spawn(config, nydusfile_dir=src.parent)
        assert egg.manifest.base_egg is None
        assert egg.manifest.min_nydus_version == "0.1.0"


class TestDirectives:
    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_exclude(self, _gl, src: Path):
        config = _oc_config(src, redact=False, excluded_memory_labels=[MemoryLabel.STATE])
        egg, _, _ = spawn(config, nydusfile_dir=src.parent)
        assert not any(m.label == MemoryLabel.STATE for m in egg.memory.memory)

    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_custom_label(self, _gl, src: Path):
        config = _oc_config(src, redact=False, custom_labels={"soul.md": "flow"})
        egg, _, _ = spawn(config, nydusfile_dir=src.parent)
        soul_records = [m for m in egg.memory.memory if m.source_store == "soul.md"]
        assert all(m.label == MemoryLabel.FLOW for m in soul_records)

    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_remove_file(self, _gl, src: Path):
        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=False,
            source_remove_globs=["soul.md"],
        )
        egg, raw, _ = spawn(config, nydusfile_dir=src.parent)
        assert "soul.md" not in raw


class TestEmptySource:
    @patch("pynydus.engine.pipeline.ensure_gitleaks_if_needed")
    def test_empty_dir(self, _gl, tmp_path: Path):
        config = _oc_config(tmp_path, redact=False)
        egg, _, _ = spawn(config, nydusfile_dir=tmp_path)
        assert len(egg.skills.skills) == 0
        assert len(egg.memory.memory) == 0
