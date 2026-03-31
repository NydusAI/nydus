"""Sphinx configuration for pynydus documentation."""

project = "pynydus"
copyright = "2026, Nydus Contributors"
author = "Jae Sim"
release = "0.1.0"

extensions = [
    "autodoc2",
    "myst_parser",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

autodoc2_packages = ["../pynydus"]
autodoc2_render_plugin = "myst"

myst_enable_extensions = [
    "colon_fence",
    "fieldlist",
    "deflist",
]

html_theme = "furo"
html_title = "pynydus"
html_logo = "_static/logo.png"
html_theme_options = {
    "source_repository": "https://github.com/NydusAI/nydus",
    "source_branch": "main",
    "source_directory": "docs/",
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
}

exclude_patterns = ["_build"]

suppress_warnings = ["ref.duplicate", "duplicate"]
