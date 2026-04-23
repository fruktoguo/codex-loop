#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/fruktoguo/codex-loop.git"
MARKETPLACE_SOURCE="fruktoguo/codex-loop"

read_version() {
  local repo_path="$1"
  python3 - "$repo_path" <<'PY'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
plugin_json = repo / "plugins" / "codex-loop" / ".codex-plugin" / "plugin.json"
try:
    payload = json.loads(plugin_json.read_text(encoding="utf-8"))
except Exception:
    print("unknown")
else:
    print(payload.get("version") or "unknown")
PY
}

if [[ "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  ./install.sh
  ./install.sh --source /path/to/codex-loop

You can also run:
  bash <(curl -fsSL https://raw.githubusercontent.com/fruktoguo/codex-loop/main/install.sh)
EOF
  exit 0
fi

SOURCE_PATH=""
if [[ "${1:-}" == "--source" ]]; then
  SOURCE_PATH="${2:-}"
  if [[ -z "$SOURCE_PATH" ]]; then
    echo "missing value for --source" >&2
    exit 1
  fi
fi

if [[ -n "$SOURCE_PATH" ]]; then
  VERSION="$(read_version "$SOURCE_PATH")"
  echo "Installing codex-loop v$VERSION from $SOURCE_PATH"
  exec python3 "$SOURCE_PATH/scripts/install.py" --source "$SOURCE_PATH" --marketplace-source "$SOURCE_PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/scripts/install.py" && -f "$SCRIPT_DIR/.agents/plugins/marketplace.json" ]]; then
  VERSION="$(read_version "$SCRIPT_DIR")"
  echo "Installing codex-loop v$VERSION from $SCRIPT_DIR"
  exec python3 "$SCRIPT_DIR/scripts/install.py" --source "$SCRIPT_DIR" --marketplace-source "$SCRIPT_DIR"
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

git clone --depth 1 "$REPO_URL" "$TMP_DIR/repo" >/dev/null 2>&1
VERSION="$(read_version "$TMP_DIR/repo")"
echo "Installing codex-loop v$VERSION from $REPO_URL"
exec python3 "$TMP_DIR/repo/scripts/install.py" --source "$TMP_DIR/repo" --marketplace-source "$MARKETPLACE_SOURCE"
