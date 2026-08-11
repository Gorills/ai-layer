#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="local-ai-development-layer"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
RUNTIME_HOME="${AI_LAYER_RUNTIME_HOME:-$DATA_HOME/ai-layer}"
RELEASES_DIR="$RUNTIME_HOME/releases"
CURRENT_LINK="$RUNTIME_HOME/current"
BIN_DIR="${AI_LAYER_BIN_DIR:-$HOME/.local/bin}"
STATE_HOME="${AI_LAYER_HOME:-$HOME/.ai-layer}"
MACHINE_RUNTIME="$STATE_HOME/runtime"
SKIP_DB=0
NO_SYNC=0
NO_SERVICE=0
KEEP_RELEASES=3

usage() {
  cat <<EOF
Usage: ./install.sh [options]

Installs or upgrades Local AI Development Layer for the current user.
Run this same command from every newly downloaded release archive.

Options:
  --skip-db          Install/update AI Layer without starting PostgreSQL.
  --no-sync          Do not automatically repair/sync registered projects.
  --no-service       Do not install/start the persistent core/dashboard user service.
  --keep-releases N  Keep N previous runtime releases (default: 3).
  -h, --help         Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-db) SKIP_DB=1; shift ;;
    --no-sync) NO_SYNC=1; shift ;;
    --no-service) NO_SERVICE=1; shift ;;
    --keep-releases)
      if [[ $# -lt 2 || ! "$2" =~ ^[0-9]+$ ]]; then
        echo "ERROR: --keep-releases requires a non-negative integer." >&2
        exit 2
      fi
      KEEP_RELEASES="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

path_exists() {
  [[ -e "$1" || -L "$1" ]]
}

runtime_assets_owned() {
  local path="$1"
  [[ -d "$path" && ! -L "$path" ]] || return 1
  [[ -f "$path/alembic.ini" && -f "$path/docker-compose.yml" ]]
}

release_target_owned() {
  local target="$1"
  case "$target" in
    "$RELEASES_DIR"/*) ;;
    *) return 1 ;;
  esac
  [[ -d "$target" && ! -L "$target" && -f "$target/pyvenv.cfg" && -x "$target/bin/ai-layer" && -x "$target/bin/ai-layer-mcp" ]] || return 1
  find "$target/lib" -path '*/site-packages/local_ai_development_layer-*.dist-info/METADATA' -type f -print -quit 2>/dev/null | grep -q .
}

launcher_owned() {
  local path="$1" name="$2" target
  [[ -L "$path" ]] || return 1
  target="$(readlink "$path")"
  if [[ "$target" == "$CURRENT_LINK/bin/$name" ]]; then
    return 0
  fi
  case "$target" in
    "$RELEASES_DIR"/*/bin/"$name") return 0 ;;
    *) return 1 ;;
  esac
}

state_home_recognizably_owned() {
  if [[ -f "$STATE_HOME/install.json" ]] && grep -q '"runtime_home"' "$STATE_HOME/install.json" 2>/dev/null && grep -q '"version"' "$STATE_HOME/install.json" 2>/dev/null; then
    return 0
  fi
  if [[ -f "$STATE_HOME/projects.json" ]] && grep -q '"projects"' "$STATE_HOME/projects.json" 2>/dev/null; then
    return 0
  fi
  runtime_assets_owned "$MACHINE_RUNTIME"
}

assert_install_paths_safe() {
  local path name target
  if [[ -L "$RELEASES_DIR" ]]; then
    echo "ERROR: refusing symlinked AI Layer releases directory: $RELEASES_DIR" >&2
    exit 1
  fi
  if [[ -e "$STATE_HOME" && ! -d "$STATE_HOME" ]]; then
    echo "ERROR: AI Layer state home is not a directory: $STATE_HOME" >&2
    exit 1
  fi
  for name in ai-layer ai-layer-mcp; do
    path="$BIN_DIR/$name"
    if path_exists "$path" && ! launcher_owned "$path" "$name"; then
      echo "ERROR: refusing to overwrite unowned launcher: $path" >&2
      exit 1
    fi
  done

  for path in "$CURRENT_LINK" "$RUNTIME_HOME/current.next"; do
    if ! path_exists "$path"; then
      continue
    fi
    if [[ ! -L "$path" ]]; then
      echo "ERROR: refusing to replace unowned runtime pointer: $path" >&2
      exit 1
    fi
    target="$(readlink "$path")"
    if ! release_target_owned "$target"; then
      echo "ERROR: refusing to replace runtime pointer outside AI Layer releases: $path -> $target" >&2
      exit 1
    fi
  done

  for path in "$MACHINE_RUNTIME" "$STATE_HOME/runtime.previous"; do
    if path_exists "$path" && ! runtime_assets_owned "$path"; then
      echo "ERROR: refusing to replace unrecognized machine runtime assets: $path" >&2
      exit 1
    fi
  done

  if [[ -d "$STATE_HOME" ]] && [[ -n "$(find "$STATE_HOME" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]] && ! state_home_recognizably_owned; then
    echo "ERROR: refusing to install into non-empty unrecognized AI Layer state home: $STATE_HOME" >&2
    exit 1
  fi
}

# Ownership preflight happens before Python/package installation so a conflicting user-owned
# path can never be modified as a side effect of a failed or partial install.
assert_install_paths_safe

find_python() {
  local candidate
  for candidate in python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" - <<'PY' >/dev/null 2>&1
import platform, sys
ok = platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 12)
raise SystemExit(0 if ok else 1)
PY
      then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "ERROR: this reproducible runtime is released for Linux x86_64 only." >&2
  echo "A separate tested lock is required before enabling another OS/architecture." >&2
  exit 1
fi

PYTHON_BIN="$(find_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: CPython 3.12.x is required by this release lock." >&2
  echo "Install CPython 3.12 and rerun ./install.sh." >&2
  exit 1
fi

VERSION="$($PYTHON_BIN - "$SOURCE_DIR/pyproject.toml" <<'PY'
import pathlib, sys, tomllib
with pathlib.Path(sys.argv[1]).open('rb') as f:
    print(tomllib.load(f)['project']['version'])
PY
)"
LOCK_FILE="$SOURCE_DIR/release/requirements-linux-x86_64-py312.lock"
WHEEL_FILE="$SOURCE_DIR/dist/local_ai_development_layer-$VERSION-py3-none-any.whl"

# Dependency-free release preflight. This MUST run before creating a venv: a clean machine
# does not have AI Layer runtime dependencies yet. Full source/skill/architecture validation
# runs inside the freshly installed isolated runtime before activation.
if ! BOOTSTRAP_PREFLIGHT_OUTPUT="$("$PYTHON_BIN" "$SOURCE_DIR/scripts/bootstrap_release_gate.py" --json 2>&1)"; then
  printf '%s\n' "$BOOTSTRAP_PREFLIGHT_OUTPUT" >&2
  echo "ERROR: release archive preflight failed before installation." >&2
  exit 1
fi
if [[ ! -f "$LOCK_FILE" || ! -f "$WHEEL_FILE" ]]; then
  echo "ERROR: release lock or application wheel is missing; archive is incomplete." >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RELEASE_DIR="$RELEASES_DIR/$VERSION-$STAMP"
if path_exists "$RELEASE_DIR"; then
  echo "ERROR: refusing to reuse unexpected release path: $RELEASE_DIR" >&2
  exit 1
fi
mkdir -p "$RELEASES_DIR" "$BIN_DIR" "$STATE_HOME"

RELEASE_ACTIVATED=0
cleanup_incomplete_release() {
  local status=$?
  if [[ $status -ne 0 && "$RELEASE_ACTIVATED" -eq 0 ]] && [[ -n "${RELEASE_DIR:-}" ]] && [[ -d "$RELEASE_DIR" ]] && [[ ! -L "$RELEASE_DIR" ]]; then
    rm -rf "$RELEASE_DIR"
  fi
  return "$status"
}
trap cleanup_incomplete_release EXIT

echo "==> Installing AI Layer $VERSION into isolated reproducible runtime"
"$PYTHON_BIN" -m venv "$RELEASE_DIR"

# Closed-world install: every runtime distribution is exact-pinned in the release lock.
# --no-deps prevents pip from silently resolving a newer transitive dependency; --only-binary
# avoids local source builds with machine-dependent build toolchains. Any missing/incompatible
# package makes the installation fail before the `current` symlink is changed.
PIP_DISABLE_PIP_VERSION_CHECK=1 "$RELEASE_DIR/bin/python" -m pip install \
  --no-cache-dir --only-binary=:all: --no-deps -r "$LOCK_FILE"
PIP_DISABLE_PIP_VERSION_CHECK=1 "$RELEASE_DIR/bin/python" -m pip install \
  --no-cache-dir --no-deps "$WHEEL_FILE"
"$RELEASE_DIR/bin/python" -m pip check
"$RELEASE_DIR/bin/python" "$SOURCE_DIR/scripts/verify_release_lock.py" \
  --lock "$LOCK_FILE" --app-version "$VERSION"

# Now that the exact runtime dependencies exist, run the complete release validation.
# This includes production Skill contracts and may import application modules. Activation
# remains impossible until this gate passes.
if ! FULL_RELEASE_GATE_OUTPUT="$("$RELEASE_DIR/bin/python" "$SOURCE_DIR/scripts/release_gate.py" --json 2>&1)"; then
  printf '%s\n' "$FULL_RELEASE_GATE_OUTPUT" >&2
  echo "ERROR: full release validation failed inside the isolated runtime; activation was not changed." >&2
  exit 1
fi

# Runtime assets are persistent because the downloaded release folder may be deleted afterwards.
RUNTIME_NEW="$STATE_HOME/runtime.new.$$"
if path_exists "$RUNTIME_NEW"; then
  echo "ERROR: refusing to replace unexpected temporary runtime path: $RUNTIME_NEW" >&2
  exit 1
fi
mkdir -p "$RUNTIME_NEW"
cp "$SOURCE_DIR/docker-compose.yml" "$RUNTIME_NEW/docker-compose.yml"
cp "$SOURCE_DIR/alembic.ini" "$RUNTIME_NEW/alembic.ini"
cp -a "$SOURCE_DIR/alembic" "$RUNTIME_NEW/alembic"
if [[ -d "$MACHINE_RUNTIME" ]]; then
  rm -rf "$STATE_HOME/runtime.previous"
  cp -a "$MACHINE_RUNTIME" "$STATE_HOME/runtime.previous"
fi
rm -rf "$MACHINE_RUNTIME"
mv "$RUNTIME_NEW" "$MACHINE_RUNTIME"

# Switch code atomically only after the new environment installed successfully.
ln -sfn "$RELEASE_DIR" "$RUNTIME_HOME/current.next"
mv -Tf "$RUNTIME_HOME/current.next" "$CURRENT_LINK"
RELEASE_ACTIVATED=1
ln -sfn "$CURRENT_LINK/bin/ai-layer" "$BIN_DIR/ai-layer"
ln -sfn "$CURRENT_LINK/bin/ai-layer-mcp" "$BIN_DIR/ai-layer-mcp"

export AI_LAYER_RUNTIME_HOME="$RUNTIME_HOME"
export AI_LAYER_MCP_EXECUTABLE="$CURRENT_LINK/bin/ai-layer-mcp"

UPGRADE_ARGS=()
[[ "$SKIP_DB" -eq 1 ]] && UPGRADE_ARGS+=(--skip-db)
[[ "$NO_SYNC" -eq 1 ]] && UPGRADE_ARGS+=(--no-sync)

set +e
UPGRADE_OUTPUT="$("$CURRENT_LINK/bin/ai-layer" upgrade "${UPGRADE_ARGS[@]}" 2>&1)"
UPGRADE_STATUS=$?
set -e

MACHINE_DOCTOR_OUTPUT=""
if [[ $UPGRADE_STATUS -eq 0 && $SKIP_DB -eq 0 ]]; then
  set +e
  MACHINE_DOCTOR_OUTPUT="$("$CURRENT_LINK/bin/ai-layer" doctor --machine-only 2>&1)"
  UPGRADE_STATUS=$?
  set -e
fi

if [[ $UPGRADE_STATUS -ne 0 ]]; then
  [[ -n "$UPGRADE_OUTPUT" ]] && printf '%s\n' "$UPGRADE_OUTPUT" >&2
  [[ -n "$MACHINE_DOCTOR_OUTPUT" ]] && printf '%s\n' "$MACHINE_DOCTOR_OUTPUT" >&2
  echo "ERROR: machine bootstrap/doctor did not complete." >&2
  # Do not roll the executable backward after `ai-layer upgrade` has run. The upgrade may already
  # have committed a forward-only Alembic migration, and pairing that newer schema with the old
  # executable is less safe than leaving one coherent forward version installed. Runtime.previous
  # is retained for diagnostics/assets only; rerun `ai-layer upgrade` after fixing the dependency.
  echo "The new executable remains active to preserve code/schema compatibility." >&2
  echo "Fix the reported dependency/problem and run: ai-layer upgrade" >&2
  exit "$UPGRADE_STATUS"
fi

# `ai-layer upgrade` already synchronizes and repairs every registered project. Present a compact
# summary instead of forcing normal users to interpret the machine-readable upgrade payload.
if [[ -n "$UPGRADE_OUTPUT" ]]; then
  printf '%s' "$UPGRADE_OUTPUT" | "$PYTHON_BIN" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
repair = data.get("project_repair") or {}
if repair.get("skipped"):
    print("==> Registered project repair skipped: " + str(repair.get("reason", "disabled")))
else:
    print("==> Registered projects: checked={0}, healthy={1}, nested-detached={2}".format(
        repair.get("projects_checked", 0), repair.get("projects_healthy", 0), repair.get("nested_detached", 0)
    ))
'
fi

# Force IDE hosts to drop any MCP process that still has the previous release loaded.
# This runs only after the new release, DB migrations, global integrations and machine-only doctor succeeded.
MCP_STOP_JSON="$("$CURRENT_LINK/bin/ai-layer" mcp-stop 2>/dev/null || true)"
if [[ -n "$MCP_STOP_JSON" ]]; then
  echo "==> Refreshed long-lived AI Layer MCP runtime: $MCP_STOP_JSON"
fi

# Safe project repair already ran during upgrade. This final all-project check is deliberately
# non-fatal for installation: remaining failures concern user-owned project content and are printed
# with exact paths/actions rather than rolling back an otherwise healthy machine runtime.
set +e
PROJECT_HEALTH_OUTPUT="$("$CURRENT_LINK/bin/ai-layer" doctor --all-projects 2>&1)"
PROJECT_HEALTH_STATUS=$?
set -e
if [[ $PROJECT_HEALTH_STATUS -eq 0 ]]; then
  echo "==> All registered projects are healthy."
else
  echo "==> AI Layer installed successfully; some project-owned content still needs attention:"
  printf '%s' "$PROJECT_HEALTH_OUTPUT" | "$PYTHON_BIN" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
for issue in data.get("issues", []):
    if issue.get("severity") != "error":
        continue
    print("  - " + str(issue.get("problem", "project issue")))
    details = issue.get("details") or {}
    for key in ("repository_ai_artifacts", "tracked_ai_or_provenance", "tracked_unscannable"):
        values = details.get(key) or []
        if values:
            print("      " + key + ": " + ", ".join(map(str, values)))
    violations = details.get("changed_privacy_violations") or []
    if violations:
        paths = [str(v.get("path")) for v in violations if v.get("path")]
        if paths:
            print("      changed_privacy_violations: " + ", ".join(paths))
    if issue.get("action"):
        print("      action: " + str(issue.get("action")))
'
fi

# Keep the visual control center available independently of MCP/terminal sessions. On Linux desktop
# systems this installs a user-level systemd service. Headless/container environments may not have
# a user manager; that is reported as a warning and does not invalidate an otherwise healthy install.
if [[ "$NO_SERVICE" -eq 0 ]]; then
  set +e
  SERVICE_OUTPUT="$("$CURRENT_LINK/bin/ai-layer" service install 2>&1)"
  SERVICE_STATUS=$?
  set -e
  if [[ $SERVICE_STATUS -eq 0 ]]; then
    echo "==> Persistent core/dashboard service enabled at http://127.0.0.1:8765/dashboard"
  else
    echo "==> Dashboard autostart was not enabled in this session (AI Layer remains installed)."
    [[ -n "$SERVICE_OUTPUT" ]] && printf '%s\n' "$SERVICE_OUTPUT"
    echo "    Start manually with: ai-layer service run"
  fi
else
  "$CURRENT_LINK/bin/ai-layer" service uninstall >/dev/null 2>&1 || true
  echo "==> Persistent core/dashboard service disabled (--no-service)."
fi

rm -rf "$STATE_HOME/runtime.previous"

# Retain a few previous release environments for rollback/diagnostics, remove older ones.
if [[ "$KEEP_RELEASES" =~ ^[0-9]+$ ]]; then
  OWNED_RELEASES=()
  while IFS= read -r candidate; do
    if [[ -d "$candidate" && ! -L "$candidate" ]] && release_target_owned "$candidate"; then
      OWNED_RELEASES+=("$candidate")
    fi
  done < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | sed 's/^[^ ]* //')
  for ((i=KEEP_RELEASES; i<${#OWNED_RELEASES[@]}; i++)); do
    release="${OWNED_RELEASES[$i]}"
    [[ -n "$release" && "$release" != "$RELEASE_DIR" ]] && rm -rf "$release"
  done
fi

cat <<EOF

AI Layer $VERSION installed successfully.
Commands:
  ai-layer doctor --all-projects
  cd <project> && ai-layer init && ai-layer scan             # standard attachment
  cd <project> && ai-layer init --external && ai-layer scan  # zero-footprint attachment
  cd <project> && ai-layer init --private && ai-layer scan   # zero-footprint + provenance/privacy enforcement
  ai-layer repair                                             # safely re-check/repair all registered projects
  ai-layer dashboard                                          # open the always-on visual dashboard
  ai-layer service status                                     # background service/autostart state
  ai-layer monitor                                            # terminal fallback for live observability

Stable runtime: $CURRENT_LINK
Persistent state: $STATE_HOME
EOF

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  cat <<EOF

NOTE: $BIN_DIR is not in the current shell PATH.
Add it to your shell profile, for example:
  export PATH="$BIN_DIR:\$PATH"
EOF
fi
