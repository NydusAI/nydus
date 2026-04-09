#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Step 1: Spawn the base chatbot ==="
cd base
uv run nydus spawn -o base.egg
uv run nydus inspect base.egg
cd ..

echo ""
echo "=== Step 2: Extend with ADD directives (FROM-only) ==="
cd extend
uv run nydus spawn -o extended.egg
uv run nydus inspect extended.egg --secrets
cd ..

echo ""
echo "=== Step 3: Diff base vs extended ==="
uv run nydus diff base/base.egg extend/extended.egg

echo ""
echo "=== Step 4: Hatch the extended egg ==="
uv run nydus hatch extend/extended.egg --target openclaw -o ./hatched/
find hatched/ -type f | sort
