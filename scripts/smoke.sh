#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() {
  if [[ -n "${DEMO_ROOT:-}" ]]; then
    ai-layer projects unregister "$DEMO_ROOT" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT
cd "$ROOT"

docker compose up -d
for _ in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U ai_layer -d ai_layer >/dev/null 2>&1; then break; fi
  sleep 1
done
ai-layer db-init
ai-layer install

mkdir -p "$TMP/demo/src"
cat > "$TMP/demo/pyproject.toml" <<'PY'
[project]
name = "demo"
version = "0.1.0"
dependencies = ["fastapi"]
PY
cat > "$TMP/demo/src/app.py" <<'PY'
from fastapi import FastAPI

app = FastAPI()

@app.get('/health')
def health():
    return {'ok': True}
PY
export DEMO_ROOT="$TMP/demo"

(
  cd "$DEMO_ROOT"
  ai-layer init

  # Static workflow is global-native. Standard projects get only sparse workspace MCP bindings,
  # never duplicate AI Layer text rules in AGENTS/CLAUDE/Cursor/Antigravity rule surfaces.
  test -f .cursor/mcp.json
  test -f .mcp.json
  test -f .codex/config.toml
  test -f .agents/mcp_config.json
  test ! -e .cursor/rules/ai-layer.mdc
  test ! -e .agents/rules/ai-layer.md
  if [[ -f AGENTS.md ]]; then ! grep -q 'Local AI Development Layer' AGENTS.md; fi
  if [[ -f CLAUDE.md ]]; then ! grep -q 'Local AI Development Layer' CLAUDE.md; fi
  grep -q 'AI_LAYER_PROJECT_ROOT' .cursor/mcp.json
  grep -q 'AI_LAYER_PROJECT_ROOT' .mcp.json
  grep -q 'AI_LAYER_PROJECT_ROOT' .codex/config.toml
  grep -q 'AI_LAYER_PROJECT_ROOT' .agents/mcp_config.json

  ai-layer scan
  ai-layer memory status --path "$DEMO_ROOT" > "$TMP/memory-status.json"

  # Scanner evidence does not become a parallel raw-source semantic memory index.
  ai-layer memory search "FastAPI health endpoint" --path "$DEMO_ROOT" > "$TMP/memory-search.json"

  ai-layer session save \
    --goal "Smoke test" \
    --state "Initial scaffold exists" \
    --done "Initialized and scanned demo" \
    --next "Continue implementation" \
    --fact "Health endpoint exists" \
    --path "$DEMO_ROOT"
  ai-layer session restore latest --path "$DEMO_ROOT" | grep -q "Smoke test"
)

python - <<'PY'
import json
import os
from pathlib import Path

from ai_layer.application.context import search_knowledge
from ai_layer.application.knowledge import status as knowledge_status
from ai_layer.application.project_intelligence import project_status

root = Path(os.environ["DEMO_ROOT"])
state = knowledge_status(root)
assert state["verified"] == 0, state
assert state["baseline_ready"] is False, state
assert state["onboarding_recommended"] is True, state
assert search_knowledge(root, "FastAPI health endpoint") == [], "scan must not index current source as Project Knowledge"

status_payload = project_status(root)
assert status_payload["agent_contract"]["startup"]["tool"] == "project_status", status_payload
assert status_payload["guidance"]["execution_owner"] == "host-native agent runtime", status_payload
assert status_payload["work"]["continuation"]["kind"] == "none", status_payload["work"]
assert status_payload["guidance"]["project_map"]["read"]["tool"] == "project_search", status_payload
assert status_payload["guidance"]["project_map"]["update"]["tool"] == "project_map_reconcile", status_payload
print("bootstrap/policy/project-intelligence smoke PASS")
PY

printf '\nSMOKE PASS\n'
