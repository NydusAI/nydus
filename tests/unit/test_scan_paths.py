"""Tests for file classification (``pynydus.common.scan_paths``)."""

from pynydus.common.scan_paths import classify, partition_files


class TestClassify:
    def test_ignored_binary(self):
        assert classify("photo.png") == "ignored"
        assert classify("archive.zip") == "ignored"
        assert classify("font.woff2") == "ignored"
        assert classify("model.bin") == "ignored"

    def test_structured(self):
        assert classify("config.json") == "structured"
        assert classify("values.yaml") == "structured"
        assert classify("data.yml") == "structured"

    def test_markdown(self):
        assert classify("README.md") == "markdown"
        assert classify("doc.mdx") == "markdown"

    def test_plain(self):
        assert classify("script.py") == "plain"
        assert classify("code.ts") == "plain"
        assert classify("Makefile") == "plain"
        assert classify("SOUL.md") == "markdown"

    def test_no_extension(self):
        assert classify("Dockerfile") == "plain"

    def test_case_insensitive_extension(self):
        assert classify("image.PNG") == "ignored"
        assert classify("data.JSON") == "structured"
        assert classify("notes.MD") == "markdown"


class TestPartitionFiles:
    def test_splits_correctly(self):
        files = {
            "SOUL.md": "text",
            "config.json": "{}",
            "photo.png": "binary",
            "code.py": "x = 1",
        }
        scannable, ignored = partition_files(files)
        assert "photo.png" in ignored
        assert "photo.png" not in scannable
        assert "SOUL.md" in scannable
        assert "config.json" in scannable
        assert "code.py" in scannable

    def test_empty_input(self):
        scannable, ignored = partition_files({})
        assert scannable == {}
        assert ignored == {}

    def test_all_ignored(self):
        files = {"a.png": "x", "b.jpg": "y"}
        scannable, ignored = partition_files(files)
        assert len(scannable) == 0
        assert len(ignored) == 2

    def test_all_scannable(self):
        files = {"a.py": "x", "b.md": "y", "c.json": "z"}
        scannable, ignored = partition_files(files)
        assert len(scannable) == 3
        assert len(ignored) == 0
