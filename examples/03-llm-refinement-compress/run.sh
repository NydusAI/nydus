#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Step 1: Spawn WITHOUT LLM refinement ==="
(
  unset NYDUS_LLM_TYPE NYDUS_LLM_API_KEY 2>/dev/null || true
  uv run nydus spawn -o verbose.egg
)
uv run nydus inspect verbose.egg

echo ""
echo "=== Step 2: Spawn WITH LLM refinement ==="
if [ -z "${NYDUS_LLM_TYPE:-}" ]; then
  echo "⚠ Set NYDUS_LLM_TYPE and NYDUS_LLM_API_KEY to enable refinement."
  echo "  Example:"
  echo "    export NYDUS_LLM_TYPE=openai/gpt-4o"
  echo "    export NYDUS_LLM_API_KEY=sk-..."
  echo ""
  echo "Skipping compressed spawn. You can still inspect verbose.egg."
  exit 0
fi
uv run nydus spawn -o compressed.egg
uv run nydus inspect compressed.egg

echo ""
echo "=== Step 3: Diff the two eggs ==="
uv run nydus diff verbose.egg compressed.egg

echo ""
echo "=== Step 4: Hatch both and compare word counts ==="
uv run nydus hatch verbose.egg --target openclaw -o ./hatched-verbose/
uv run nydus hatch compressed.egg --target openclaw -o ./hatched-compressed/

echo ""
echo "--- Verbose output ---"
find hatched-verbose/ -name '*.md' -exec cat {} + 2>/dev/null | wc -w || echo "(no md files)"
echo "--- Compressed output ---"
find hatched-compressed/ -name '*.md' -exec cat {} + 2>/dev/null | wc -w || echo "(no md files)"
