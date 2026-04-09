"""Sphinx configuration for PyNydus documentation."""

import re
from pathlib import Path

_docs_dir = Path(__file__).resolve().parent
_root = _docs_dir.parent
_pyproject = _root / "pyproject.toml"
_m = re.search(r'version\s*=\s*"([^"]+)"', _pyproject.read_text(encoding="utf-8"))
_release = _m.group(1) if _m else "0.0.0"

project = "PyNydus"
copyright = "2026, Nydus Contributors"
author = "Nydus Team"
release = _release
version = _release

extensions = [
    "autodoc2",
    "myst_parser",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

autodoc2_packages = ["../pynydus"]
autodoc2_render_plugin = "myst"
# Sample agent trees under pynydus/eggs/base are not library API
autodoc2_skip_module_regexes = [r"pynydus\.eggs\."]

myst_enable_extensions = [
    "colon_fence",
    "fieldlist",
    "deflist",
]

html_theme = "furo"
html_title = "PyNydus"
html_short_title = "PyNydus"
html_logo = "_static/logo.png"
html_theme_options = {
    "source_repository": "https://github.com/NydusAI/nydus",
    "source_branch": "main",
    "source_directory": "nydus/docs/",
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
}

exclude_patterns = ["_build"]
