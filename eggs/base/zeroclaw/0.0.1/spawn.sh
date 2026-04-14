#!/usr/bin/env bash
# Build: produces ./base.egg in this directory.
# Publish (after NYDUS_REGISTRY_URL is set): nydus push ./base.egg --name nydus/zeroclaw --version 0.0.1
set -euo pipefail
cd "$(dirname "$0")"
exec uv run nydus spawn -o ./base.egg
