"""Tests for the gitleaks connector (``pynydus.security.gitleaks``)."""

from __future__ import annotations

from pathlib import Path

from pynydus.common.enums import SecretKind
from pynydus.security.gitleaks import (
    Finding,
    apply_gitleaks_findings,
    find_gitleaks,
    run_gitleaks_scan,
)


class TestFindGitleaks:
    def test_found(self, monkeypatch):
        monkeypatch.delenv("NYDUS_GITLEAKS_PATH", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gitleaks")
        assert find_gitleaks() == "/usr/bin/gitleaks"

    def test_missing(self, monkeypatch):
        monkeypatch.delenv("NYDUS_GITLEAKS_PATH", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert find_gitleaks() is None

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("NYDUS_GITLEAKS_PATH", "/opt/gitleaks")
        monkeypatch.setattr("shutil.which", lambda x: x)
        assert find_gitleaks() == "/opt/gitleaks"


class TestApplyFindings:
    def test_single_secret(self, tmp_path: Path):
        files = {"config.json": '{"api_key": "sk-secret-123"}'}
        (tmp_path / "config.json").write_text(files["config.json"])
        findings = [
            Finding(
                file=str(tmp_path / "config.json"),
                rule_id="generic-api-key",
                match="sk-secret-123",
                start_line=1,
                start_column=14,
                end_column=27,
            )
        ]
        redacted, secrets, next_idx = apply_gitleaks_findings(
            files, findings, temp_root=tmp_path, start_index=1
        )
        assert "sk-secret-123" not in redacted["config.json"]
        assert "{{SECRET_001}}" in redacted["config.json"]
        assert secrets[0].kind == SecretKind.CREDENTIAL
        assert next_idx == 2

    def test_no_findings(self, tmp_path: Path):
        files = {"readme.md": "# Hello world"}
        (tmp_path / "readme.md").write_text(files["readme.md"])
        redacted, secrets, next_idx = apply_gitleaks_findings(
            files, [], temp_root=tmp_path, start_index=1
        )
        assert redacted == files
        assert secrets == []
        assert next_idx == 1

    def test_multiple_findings(self, tmp_path: Path):
        content = '{"key1": "secret_aaa", "key2": "secret_bbb"}'
        files = {"cfg.json": content}
        (tmp_path / "cfg.json").write_text(content)
        findings = [
            Finding(
                file=str(tmp_path / "cfg.json"),
                rule_id="key1",
                match="secret_aaa",
                start_line=1,
                start_column=10,
                end_column=20,
            ),
            Finding(
                file=str(tmp_path / "cfg.json"),
                rule_id="key2",
                match="secret_bbb",
                start_line=1,
                start_column=32,
                end_column=42,
            ),
        ]
        redacted, secrets, next_idx = apply_gitleaks_findings(
            files, findings, temp_root=tmp_path, start_index=5
        )
        assert "secret_aaa" not in redacted["cfg.json"]
        assert "secret_bbb" not in redacted["cfg.json"]
        assert len(secrets) == 2
        assert next_idx == 7

    def test_dedup(self, tmp_path: Path):
        content = '"key": "same_val", "key2": "same_val"'
        files = {"f.txt": content}
        (tmp_path / "f.txt").write_text(content)
        findings = [
            Finding(
                file=str(tmp_path / "f.txt"),
                rule_id="r1",
                match="same_val",
                start_line=1,
                start_column=8,
                end_column=16,
            ),
            Finding(
                file=str(tmp_path / "f.txt"),
                rule_id="r2",
                match="same_val",
                start_line=1,
                start_column=28,
                end_column=36,
            ),
        ]
        _, secrets, _ = apply_gitleaks_findings(files, findings, temp_root=tmp_path, start_index=1)
        assert len(secrets) == 1

    def test_safe_description(self, tmp_path: Path):
        files = {"a.yml": "token: sk-super-secret-val-12345"}
        (tmp_path / "a.yml").write_text(files["a.yml"])
        findings = [
            Finding(
                file=str(tmp_path / "a.yml"),
                rule_id="openai-key",
                match="sk-super-secret-val-12345",
                start_line=1,
                start_column=7,
                end_column=32,
            )
        ]
        _, secrets, _ = apply_gitleaks_findings(files, findings, temp_root=tmp_path, start_index=1)
        assert "sk-super-secret" not in secrets[0].description
        assert "gitleaks:" in secrets[0].description

    def test_nested_paths(self, tmp_path: Path):
        nested = tmp_path / "sub" / "dir"
        nested.mkdir(parents=True)
        content = "password: hunter2"
        (nested / "cfg.yaml").write_text(content)
        files = {"sub/dir/cfg.yaml": content}
        findings = [
            Finding(
                file=str(nested / "cfg.yaml"),
                rule_id="password",
                match="hunter2",
                start_line=1,
                start_column=10,
                end_column=17,
            )
        ]
        redacted, secrets, _ = apply_gitleaks_findings(
            files, findings, temp_root=tmp_path, start_index=1
        )
        assert "hunter2" not in redacted["sub/dir/cfg.yaml"]
        assert secrets[0].occurrences == ["sub/dir/cfg.yaml"]

    def test_unknown_file(self, tmp_path: Path):
        files = {"readme.md": "clean"}
        (tmp_path / "readme.md").write_text(files["readme.md"])
        findings = [
            Finding(
                file=str(tmp_path / "other.py"),
                rule_id="r1",
                match="secret",
                start_line=1,
                start_column=1,
                end_column=7,
            )
        ]
        redacted, secrets, _ = apply_gitleaks_findings(
            files, findings, temp_root=tmp_path, start_index=1
        )
        assert redacted == files
        assert secrets == []


class TestRunScan:
    """Requires a real ``gitleaks`` binary on ``PATH`` or ``$NYDUS_GITLEAKS_PATH``."""

    def test_detects_aws_token(self, tmp_path: Path):
        (tmp_path / "leak.txt").write_text(
            "aws_access_key_id = AKIAYRWSSQ3BPTB4DX7Z\n",
            encoding="utf-8",
        )
        findings = run_gitleaks_scan(tmp_path)
        assert len(findings) >= 1
        rule_ids = {f.rule_id.lower() for f in findings}
        assert "aws-access-token" in rule_ids

    def test_clean_tree(self, tmp_path: Path):
        (tmp_path / "safe.md").write_text("# Nothing secret here\n")
        findings = run_gitleaks_scan(tmp_path)
        assert findings == []
