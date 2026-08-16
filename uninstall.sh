#!/usr/bin/env bash
set -Eeuo pipefail
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
RUNTIME_HOME="${AI_LAYER_RUNTIME_HOME:-$DATA_HOME/ai-layer}"
BIN_DIR="${AI_LAYER_BIN_DIR:-$HOME/.local/bin}"
STATE_HOME="${AI_LAYER_HOME:-$HOME/.ai-layer}"
PURGE=0

usage() {
  cat <<'USAGE'
Usage: ./uninstall.sh [--purge]

Removes the AI Layer runtime and owned launchers/integrations.
  --purge   Also remove recognized AI Layer persistent machine state.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge) PURGE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

remove_owned_launcher() {
  local path="$1" expected="$2"
  if [[ -L "$path" ]]; then
    local target
    target="$(readlink "$path" || true)"
    if [[ "$target" == "$expected" ]]; then
      rm -f "$path"
    else
      echo "WARNING: preserving non-AI-Layer launcher symlink: $path -> $target" >&2
    fi
  elif [[ -e "$path" ]]; then
    echo "WARNING: preserving non-symlink launcher not owned by AI Layer: $path" >&2
  fi
}

runtime_release_owned() {
  local path="$1"
  [[ -d "$path" && ! -L "$path" && -f "$path/pyvenv.cfg" && -x "$path/bin/ai-layer" && -x "$path/bin/ai-layer-mcp" ]] || return 1
  find "$path/lib" -path '*/site-packages/local_ai_development_layer-*.dist-info/METADATA' -type f -print -quit 2>/dev/null | grep -q .
}

runtime_pointer_owned() {
  local path="$1" target
  [[ -L "$path" ]] || return 1
  target="$(readlink "$path" || true)"
  case "$target" in
    "$RUNTIME_HOME/releases"/*) return 0 ;;
    *) return 1 ;;
  esac
}

remove_owned_runtime_pointer() {
  local path="$1"
  if [[ -L "$path" ]]; then
    if runtime_pointer_owned "$path"; then
      rm -f "$path"
    else
      echo "WARNING: preserving runtime symlink outside AI Layer releases: $path -> $(readlink "$path" || true)" >&2
    fi
  elif [[ -e "$path" ]]; then
    echo "WARNING: preserving non-symlink runtime pointer not owned by AI Layer: $path" >&2
  fi
}

state_home_owned() {
  if [[ -f "$STATE_HOME/install.json" ]] && grep -q '"runtime_home"' "$STATE_HOME/install.json" 2>/dev/null && grep -q '"version"' "$STATE_HOME/install.json" 2>/dev/null; then
    return 0
  fi
  if [[ -f "$STATE_HOME/projects.json" ]] && grep -q '"projects"' "$STATE_HOME/projects.json" 2>/dev/null; then
    return 0
  fi
  if [[ -d "$STATE_HOME/runtime" && ! -L "$STATE_HOME/runtime" && -f "$STATE_HOME/runtime/alembic.ini" && -f "$STATE_HOME/runtime/docker-compose.yml" ]]; then
    return 0
  fi
  return 1
}

CURRENT_RELEASE=""
if runtime_pointer_owned "$RUNTIME_HOME/current"; then
  CURRENT_RELEASE="$(readlink "$RUNTIME_HOME/current" || true)"
fi
if [[ -n "$CURRENT_RELEASE" ]] && runtime_release_owned "$CURRENT_RELEASE"; then
  # Remove only ownership-marked global/project adapters while a verified AI Layer release still exists.
  "$CURRENT_RELEASE/bin/ai-layer" uninstall-integrations || \
    echo "WARNING: some AI Layer integration residue could not be removed automatically; user-owned conflicts were preserved." >&2
  "$CURRENT_RELEASE/bin/ai-layer" service uninstall >/dev/null 2>&1 || true
else
  UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  # Without the runtime we cannot prove ownership of an arbitrary same-named unit. Remove only the
  # legacy/current unit when its content identifies Local AI Development Layer.
  UNIT_PATH="$UNIT_DIR/ai-layer.service"
  if [[ -f "$UNIT_PATH" && ! -L "$UNIT_PATH" ]] && grep -q 'Local AI Development Layer Service' "$UNIT_PATH" 2>/dev/null; then
    systemctl --user disable --now ai-layer.service >/dev/null 2>&1 || true
    rm -f "$UNIT_PATH"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
fi

remove_owned_launcher "$BIN_DIR/ai-layer" "$RUNTIME_HOME/current/bin/ai-layer"
remove_owned_launcher "$BIN_DIR/ai-layer-mcp" "$RUNTIME_HOME/current/bin/ai-layer-mcp"

# Runtime home can be redirected by environment variables. Never recursively delete that whole
# directory or an arbitrary `releases` directory: remove only runtime pointers/releases that carry
# concrete AI Layer ownership evidence, preserving unrelated user content on a bad/shared path.
remove_owned_runtime_pointer "$RUNTIME_HOME/current"
remove_owned_runtime_pointer "$RUNTIME_HOME/current.next"
if [[ -d "$RUNTIME_HOME/releases" && ! -L "$RUNTIME_HOME/releases" ]]; then
  while IFS= read -r -d '' release; do
    if runtime_release_owned "$release"; then
      rm -rf "$release"
    else
      echo "WARNING: preserving unrecognized release directory: $release" >&2
    fi
  done < <(find "$RUNTIME_HOME/releases" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)
  rmdir "$RUNTIME_HOME/releases" 2>/dev/null || true
elif [[ -L "$RUNTIME_HOME/releases" ]]; then
  echo "WARNING: preserving symlinked releases directory: $RUNTIME_HOME/releases" >&2
fi
rmdir "$RUNTIME_HOME" 2>/dev/null || true

if [[ $PURGE -eq 1 ]]; then
  if [[ -d "$STATE_HOME" ]]; then
    if ! state_home_owned; then
      echo "ERROR: refusing --purge because $STATE_HOME is not recognizably AI Layer-owned." >&2
      exit 1
    fi
    rm -f \
      "$STATE_HOME/config.yaml" "$STATE_HOME/install.json" "$STATE_HOME/install-journal.json" \
      "$STATE_HOME/projects.json" \
      "$STATE_HOME/projects.json.lock" "$STATE_HOME/skill-registry.json" "$STATE_HOME/.skill-registry.lock" \
      "$STATE_HOME/agent-policy.json"
    rm -rf \
      "$STATE_HOME/projects" "$STATE_HOME/skills" "$STATE_HOME/project-skills" \
      "$STATE_HOME/skill-imports" "$STATE_HOME/skill-inbox" "$STATE_HOME/skill-packages" \
      "$STATE_HOME/policies" "$STATE_HOME/runtime" "$STATE_HOME/runtime.previous" \
      "$STATE_HOME/review-sandboxes" "$STATE_HOME/mcp-processes" "$STATE_HOME/recovery" \
      "$STATE_HOME/observability"
    rmdir "$STATE_HOME" 2>/dev/null || true
  fi
  echo "AI Layer runtime and recognized persistent state removed. Docker volume was not deleted automatically."
else
  echo "AI Layer runtime removed. Persistent ~/.ai-layer state and PostgreSQL volume were preserved."
fi
