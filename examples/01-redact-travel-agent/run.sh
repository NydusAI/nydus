#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Step 1: Spawn (gitleaks + Presidio redaction) ==="
uv run nydus spawn -o travel.egg

echo ""
echo "=== Step 2: Inspect — see what got redacted ==="
uv run nydus inspect travel.egg --secrets

echo ""
echo "=== Step 3: Generate .env template from egg ==="
uv run nydus env travel.egg -o hatch.env
echo "--- Template (empty values) ---"
cat hatch.env

echo ""
echo "=== Step 4: Fill .env with demo values ==="
# Fill every empty NAME= line with a demo placeholder value.
# In production you'd fill these with real secrets.
sed 's/^\([A-Z_]*\)=$/\1=demo-restored-value/' hatch.env > hatch.env.filled
echo "--- Filled ---"
cat hatch.env.filled

echo ""
echo "=== Step 5: Hatch with secrets injected (rebuild mode) ==="
uv run nydus hatch travel.egg --target openclaw -o ./hatched-rebuild/ --secrets hatch.env.filled

echo ""
echo "=== Step 6: Hatch with passthrough (preserves original structure) ==="
uv run nydus hatch travel.egg --target openclaw -o ./hatched-passthrough/ --passthrough --secrets hatch.env.filled

echo ""
echo "=== Step 7: Compare structures ==="
echo "--- Source files ---"
find openclaw/ -type f | sort
echo "--- Rebuild output ---"
find hatched-rebuild/ -type f | sort
echo "--- Passthrough output (preserved) ---"
find hatched-passthrough/ -type f | sort
